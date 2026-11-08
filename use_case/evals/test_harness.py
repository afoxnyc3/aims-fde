"""Pins what the scorers must catch and must not. No model calls.

    uv run --project 01_Product_Engineering/challenge python -m unittest discover -s use_case/evals
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import harness as evals  # noqa: E402
import run  # noqa: E402

CASES = {case["id"]: case for case in evals.load_cases()}


def question(answer=None, declined=False, reason=None, sources=()):
    return json.dumps({"declined": declined, "answer": answer, "decline_reason": reason, "sources": list(sources)})


class OracleAndEcho(unittest.TestCase):
    def test_oracle_scores_one_on_every_raw_mean(self):
        cases = evals.load_cases()
        report = evals.run_eval(cases, run.make_oracle(cases), "oracle")
        self.assertEqual(report.means, {label: 1.0 for label in evals.SCORERS})

    def test_echo_never_passes_the_headline(self):
        cases = evals.load_cases()
        self.assertEqual(evals.run_eval(cases, run.echo, "echo").means["correct_behaviour"], 0.0)


class FakeJudge:
    """Records what the judge was asked, with no model call."""

    def __init__(self):
        self.seen = []

    def score(self, said, case):
        self.seen.append((said, case))
        return 1.0


class Grounded(unittest.TestCase):
    def setUp(self):
        pages = {"STD-x": "sentinel-standard", "SYN-1a": "sentinel-cited", "SYN-2b": "sentinel-uncited"}
        patcher = mock.patch.object(evals, "_PAGES", pages)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.judge = FakeJudge()
        self.grounded = evals.make_grounded(self.judge)

    def test_a_ticket_is_not_judged(self):
        self.assertEqual(self.grounded("{}", CASES["DEMO-001"]), 1.0)
        self.assertEqual(self.judge.seen, [])

    def test_a_decline_reason_is_judged(self):
        self.grounded(question(declined=True, reason="No record says so."), CASES["q13"])
        self.assertEqual(self.judge.seen[0][0], "No record says so.")

    def test_echo_text_is_judged_as_is(self):
        self.grounded(CASES["q13"]["input"], CASES["q13"])
        self.assertEqual(self.judge.seen[0][0], CASES["q13"]["input"])

    def test_the_judge_sees_the_standard_and_the_cited_ticket(self):
        records = evals.judge_case("q?", ["SYN-1a"])["input"]
        self.assertIn("sentinel-standard", records)
        self.assertIn("sentinel-cited", records)
        self.assertNotIn("sentinel-uncited", records)

    def test_a_ticket_named_in_a_decline_reason_counts_as_cited(self):
        self.grounded(question(declined=True, reason="[SYN-1a] leaves this blank."), CASES["q13"])
        self.assertIn("sentinel-cited", self.judge.seen[0][1]["input"])

    def test_a_judge_failure_is_counted_not_hidden(self):
        class Broken:
            def score(self, said, case):
                raise TimeoutError

        grounded = evals.make_grounded(Broken())
        report = evals.run_eval([CASES["q13"]], lambda _: question("x"), "broken", {evals.grounded_label(): grounded})
        self.assertEqual(grounded.failures, 1)
        self.assertEqual(report.means[evals.grounded_label()], 0.0)

    def test_changing_the_judge_changes_the_fingerprint(self):
        before = evals.grounded_label()
        with mock.patch.object(evals, "JUDGE_MODEL", "some/other-model"):
            self.assertNotEqual(evals.grounded_label(), before)


class CleanCheckout(unittest.TestCase):
    def test_the_standard_loads_without_the_gitignored_tickets(self):
        env = {"CORPUS_PATH": "/no/such/file.jsonl", "JUDGE_CORPUS_APPROVED": "1"}
        with mock.patch.object(evals, "_PAGES", {}), mock.patch.dict(os.environ, env):
            self.assertTrue(any(name.startswith("STD-") for name in evals._pages()))

    def test_another_corpus_needs_approval_before_the_judge_reads_it(self):
        env = {"CORPUS_PATH": "/internal/real_tickets.jsonl"}
        with mock.patch.object(evals, "_PAGES", {}), mock.patch.dict(os.environ, env):
            os.environ.pop("JUDGE_CORPUS_APPROVED", None)
            with self.assertRaisesRegex(RuntimeError, "JUDGE_CORPUS_APPROVED"):
                evals._pages()

    def test_a_cited_ticket_with_no_corpus_fails_rather_than_judging_blind(self):
        with mock.patch.object(evals, "_PAGES", {"STD-x": "standard"}):
            with self.assertRaisesRegex(RuntimeError, "corpus is not available"):
                evals.judge_case("q?", ["SYN-1a"])
            self.assertIn("standard", evals.judge_case("q?", [])["input"])


class CommittedBaseline(unittest.TestCase):
    """`run.py --committed` is the clean-checkout report, so it must pass offline and catch a swapped baseline."""

    def test_the_committed_baseline_reports_pass(self):
        with mock.patch("builtins.print"):
            self.assertTrue(run.committed_report())

    def test_a_baseline_that_is_not_the_test_run_fails(self):
        with mock.patch("builtins.print"):
            self.assertFalse(run.committed_report(baseline_path=run.COMMITTED / "endpoint_dev.json"))

    def test_another_run_on_the_test_cases_fails(self):
        # oracle_test shares the baseline's fingerprint, so only the means tell them apart.
        with mock.patch("builtins.print"):
            self.assertFalse(run.committed_report(baseline_path=run.COMMITTED / "oracle_test.json"))

    def test_a_baseline_not_on_the_tc4_standard_fails(self):
        # TC4 is pinned to v0.3 (owner, 2026-11-07): a baseline recorded on a later standard must not pass.
        with tempfile.TemporaryDirectory() as d:
            data = json.loads(run.BASELINE.read_text())
            data["meta"]["standard"] = "v0.4 (private path)"
            p = Path(d) / "baseline.json"
            p.write_text(json.dumps(data))
            with mock.patch("builtins.print"):
                self.assertFalse(run.committed_report(baseline_path=p))


class ScenariosPin(unittest.TestCase):
    """--scenarios is TC4 Step 5: it must run on standard v0.3 however the standard is chosen."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.v03, self.v04 = (Path(self.dir.name) / f"v{v}.yaml" for v in ("0.3", "0.4"))
        self.v03.write_text("# private\nversion: '0.3'\nroles: []\n")
        self.v04.write_text('version: "0.4"\n')

    def preflight(self, **env):
        base = {"ONBOARDING_STANDARD": "", "ONBOARDING_STANDARD_DIR": "", "ONBOARDING_STANDARD_VERSION": ""}
        with mock.patch.dict(os.environ, {**base, **env}):
            run.scenarios_preflight()

    def test_an_explicit_v04_path_is_refused_even_with_a_matching_version(self):
        with self.assertRaises(SystemExit):
            self.preflight(ONBOARDING_STANDARD=str(self.v04), ONBOARDING_STANDARD_VERSION="0.4")
        with self.assertRaises(SystemExit):
            self.preflight(ONBOARDING_STANDARD=str(self.v04), ONBOARDING_STANDARD_VERSION="0.3")
        with self.assertRaises(SystemExit):
            self.preflight(ONBOARDING_STANDARD=str(self.v03))  # no pin set

    def test_a_folder_needs_the_pin(self):
        with self.assertRaises(SystemExit):
            self.preflight(ONBOARDING_STANDARD_DIR=self.dir.name)
        self.preflight(ONBOARDING_STANDARD_DIR=self.dir.name, ONBOARDING_STANDARD_VERSION="0.3")

    def test_an_explicit_v03_path_with_the_pin_passes(self):
        self.preflight(ONBOARDING_STANDARD=str(self.v03), ONBOARDING_STANDARD_VERSION="0.3")
        self.assertEqual(run.declared_version(str(self.v04)), "0.4")


class UnnecessaryAsks(unittest.TestCase):
    """An ask is unnecessary when the endpoint says needs_information and the label is recommended."""

    def test_the_definition(self):
        self.assertTrue(evals.unnecessary_ask({"status": "recommended"}, {"status": "needs_information"}))
        self.assertFalse(evals.unnecessary_ask({"status": "needs_information"}, {"status": "needs_information"}))
        self.assertFalse(evals.unnecessary_ask({"status": "human_review"}, {"status": "needs_information"}))
        self.assertFalse(evals.unnecessary_ask({"status": "recommended"}, {"status": "human_review"}))
        self.assertFalse(evals.unnecessary_ask({"status": "recommended"}, {}))

    def test_a_missed_ask_is_the_other_direction(self):
        self.assertTrue(evals.missed_ask({"status": "needs_information"}, {"status": "recommended"}))
        self.assertFalse(evals.missed_ask({"status": "needs_information"}, {"status": "human_review"}))
        self.assertFalse(evals.missed_ask({"status": "recommended"}, {"status": "needs_information"}))

    def test_counted_from_a_saved_run_and_errors_left_out(self):
        test_run = evals.harness.load(run.COMMITTED / "endpoint_test.json")
        self.assertEqual(evals.count_asks(test_run), (8, 0, 29))
        self.assertEqual(evals.count_asks(evals.harness.load(run.COMMITTED / "endpoint_grid.json")), (0, 7, 180))
        self.assertEqual(evals.count_asks(evals.harness.load(run.COMMITTED / "oracle_test.json")), (0, 0, 29))
        test_run.results[0].error = "boom"
        self.assertEqual(evals.count_asks(test_run)[2], 28)

    def report_rows(self):
        with mock.patch("builtins.print") as printed:
            run.committed_report()
        table = printed.call_args_list[0].args[0]
        self.assertIn("| over-access | unnecessary asks | missed asks |", table)
        return {tuple(cell.strip() for cell in line.split("|")[1:3]): line for line in table.splitlines()[2:]}

    def test_the_committed_report_puts_both_beside_over_access_on_one_denominator(self):
        rows = self.report_rows()
        self.assertTrue(rows["endpoint", "test"].endswith("| 2 of 29 (7%) | 8 of 29 (28%) | 0 of 29 (0%) |"), rows["endpoint", "test"])
        self.assertTrue(rows["endpoint", "grid"].endswith("| 11 of 180 (6%) | 0 of 180 (0%) | 7 of 180 (4%) |"), rows["endpoint", "grid"])

    def test_the_name_policy_rescore_from_the_saved_outputs(self):
        # 2026-11-07: no surname goes back to the manager, so 10 recommended labels became needs_information.
        test_run = evals.harness.load(run.COMMITTED / "endpoint_test.json")
        rescored = run.rescore(test_run, run.current_labels("test"))
        self.assertEqual(sum(r.scores["status_accuracy"] for r in rescored.results), 22)
        self.assertEqual(sum(r.scores["no_over_privilege"] < 1.0 for r in rescored.results), 2)
        self.assertEqual(evals.count_asks(rescored), (0, 0, 29))
        dev = run.rescore(evals.harness.load(run.COMMITTED / "endpoint_dev.json"), run.current_labels("dev"))
        self.assertEqual(sum(r.scores["status_accuracy"] for r in dev.results), 27)
        self.assertEqual(test_run.means["status_accuracy"], 14 / 29)  # the saved run itself is untouched

    def first_with_status(self, run_report, status):
        return next(i for i, r in enumerate(run_report.results) if evals.parse(r.actual)["status"] == status)

    def test_a_recommendation_against_a_relabelled_ask_becomes_an_over_grant(self):
        test_run = evals.harness.load(run.COMMITTED / "endpoint_test.json")
        i = self.first_with_status(test_run, "recommended")
        labels = run.current_labels("test")
        labels[test_run.results[i].input] = {**labels[test_run.results[i].input], "status": "human_review"}
        self.assertEqual(run.rescore(test_run, labels).results[i].scores["no_over_privilege"], 0.0)

    def test_a_label_newly_made_recommended_is_not_passed_offline(self):
        # The private scorer checks the grant's fields; a status match alone could hide an over-grant.
        test_run = evals.harness.load(run.COMMITTED / "endpoint_test.json")
        i = self.first_with_status(test_run, "recommended")
        labels = run.current_labels("test")
        old = evals.parse(test_run.results[i].expected)
        labels[test_run.results[i].input] = {**labels[test_run.results[i].input], "status": "recommended"}
        test_run.results[i].expected = json.dumps({**old, "status": "human_review"})
        with self.assertRaises(ValueError):
            run.rescore(test_run, labels)

    def test_a_changed_grant_under_a_saved_recommendation_is_not_passed_offline(self):
        # Codex review: system_login yes -> no with the status unchanged must not keep the old over-access verdict.
        test_run = evals.harness.load(run.COMMITTED / "endpoint_test.json")
        i = self.first_with_status(test_run, "recommended")
        labels = run.current_labels("test")
        ref = test_run.results[i].input
        self.assertEqual(labels[ref]["status"], "recommended")
        labels[ref] = {**labels[ref], "system_login": "no" if labels[ref]["system_login"] == "yes" else "yes"}
        with self.assertRaises(ValueError):
            run.rescore(test_run, labels)

    def test_a_rescored_run_cannot_be_compared_to_the_baseline(self):
        test_run = evals.harness.load(run.COMMITTED / "endpoint_test.json")
        rescored = run.rescore(test_run, run.current_labels("test"))
        self.assertNotEqual(rescored.fingerprint, test_run.fingerprint)
        self.assertFalse(evals.harness.compare(evals.harness.load(run.BASELINE), rescored).passed)

    def test_an_unchanged_split_keeps_its_fingerprint_and_interval(self):
        grid = evals.harness.load(run.COMMITTED / "endpoint_grid.json")
        rescored = run.rescore(grid, run.current_labels("grid"))
        self.assertEqual((rescored.fingerprint, rescored.meta.get("ci95")), (grid.fingerprint, grid.meta.get("ci95")))

    def test_a_ticket_with_no_current_label_is_left_out_not_a_crash(self):
        test_run = evals.harness.load(run.COMMITTED / "endpoint_test.json")
        labels = run.current_labels("test")
        del labels[test_run.results[0].input]
        rescored = run.rescore(test_run, labels)
        self.assertIn("no current label", rescored.results[0].error)
        self.assertEqual(evals.count_asks(rescored)[2], 28)

    def test_dropping_a_different_ticket_changes_the_fingerprint(self):
        # Codex review: two runs that left out different cases must not compare as the same cohort.
        grid = evals.harness.load(run.COMMITTED / "endpoint_grid.json")
        prints = []
        for i in (0, 1):
            labels = run.current_labels("grid")
            del labels[grid.results[i].input]
            prints.append(run.rescore(grid, labels).fingerprint)
        self.assertNotEqual(*prints)

    def test_errored_cases_leave_every_column_and_an_all_errored_run_does_not_divide_by_zero(self):
        real_load = evals.harness.load

        def load(path):
            report = real_load(path)
            if Path(path).name == "endpoint_test.json":
                report.results[0].error = "boom"
            if Path(path).name == "echo_dev.json":
                for r in report.results:
                    r.error = "boom"
            return report

        with mock.patch.object(evals.harness, "load", side_effect=load):
            rows = self.report_rows()
        self.assertIn("| endpoint | test | 29 (1 errored) |", rows["endpoint", "test"])
        self.assertTrue(rows["endpoint", "test"].endswith("of 28 (0%) |"), rows["endpoint", "test"])
        self.assertTrue(rows["echo", "dev"].endswith("| 0 of 0 | 0 of 0 | 0 of 0 |"), rows["echo", "dev"])


class ScenariosPreflight(unittest.TestCase):
    def test_scenarios_refuse_to_run_without_the_v02_standard(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("sys.argv", ["run.py", "--scenarios"]), \
             mock.patch.object(run, "make_endpoint") as endpoint:
            with self.assertRaises(SystemExit) as stopped:
                run.main()
        self.assertIn("ONBOARDING_STANDARD", str(stopped.exception.code))
        endpoint.assert_not_called()  # no client, no model call

    def test_set_standard_passes_the_check(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "std.yaml"
            p.write_text("version: '0.3'\n")  # the TC4 pin: see ScenariosPin
            with mock.patch.dict(os.environ, {"ONBOARDING_STANDARD": str(p), "ONBOARDING_STANDARD_VERSION": "0.3"}):
                run.scenarios_preflight()


class SavedRun(unittest.TestCase):
    def test_a_long_response_stays_valid_json(self):
        long_answer = json.dumps({"declined": False, "answer": "x" * 5000, "sources": []})
        report = evals.run_eval(evals.load_cases()[:1], lambda _: long_answer, "long")
        self.assertEqual(json.loads(report.results[0].actual)["answer"], "x" * 5000)


class CorrectBehaviour(unittest.TestCase):
    def test_forbidden_phrase_in_a_decline_reason_fails(self):
        leaked = question(declined=True, reason="The temporary password: abc123 is on file.")
        self.assertEqual(evals.correct_behaviour(leaked, CASES["q10"]), 0.0)

    def test_a_clean_decline_passes(self):
        clean = question(declined=True, reason="No record holds credentials.")
        self.assertEqual(evals.correct_behaviour(clean, CASES["q10"]), 1.0)

    def test_an_over_grant_fails(self):
        out = copy.deepcopy(CASES["DEMO-001"]["output"])
        out["answer"]["permissions"] = ["admin.all"]
        self.assertEqual(evals.correct_behaviour(json.dumps(out), CASES["DEMO-001"]), 0.0)

    def test_an_added_staff_group_fails(self):
        out = copy.deepcopy(CASES["DEMO-001"]["output"])
        out["answer"]["staff_groups"] = [{"id": "group-demo-trainer-4", "name": "Trainer Level 4"}]
        self.assertEqual(evals.correct_behaviour(json.dumps(out), CASES["DEMO-001"]), 0.0)

    def test_an_empty_staff_group_list_matches_a_golden_that_omits_it(self):
        out = copy.deepcopy(CASES["DEMO-001"]["output"])
        out["answer"]["staff_groups"] = []
        self.assertEqual(evals.correct_behaviour(json.dumps(out), CASES["DEMO-001"]), 1.0)

    def test_a_proposal_where_the_golden_has_none_fails(self):
        out = copy.deepcopy(CASES["DEMO-003"]["output"])
        out["answer"] = CASES["DEMO-001"]["output"]["answer"]
        self.assertEqual(evals.correct_behaviour(json.dumps(out), CASES["DEMO-003"]), 0.0)

    def test_a_missing_proposal_fails(self):
        out = copy.deepcopy(CASES["DEMO-001"]["output"])
        out["answer"] = None
        self.assertEqual(evals.correct_behaviour(json.dumps(out), CASES["DEMO-001"]), 0.0)

    def test_the_wrong_employee_fails(self):
        out = copy.deepcopy(CASES["DEMO-001"]["output"])
        out["answer"]["person_name"] = "Example Hire D"
        self.assertEqual(evals.correct_behaviour(json.dumps(out), CASES["DEMO-001"]), 0.0)

    def test_an_invented_approver_fails(self):
        out = copy.deepcopy(CASES["DEMO-004"]["output"])
        out["approval_owner_role"] = "Hiring Manager"
        self.assertEqual(evals.correct_behaviour(json.dumps(out), CASES["DEMO-004"]), 0.0)

    def test_hyphen_and_curly_spellings_still_match(self):
        answer = "Mirror Jordan Sample; this needs human-review."
        self.assertEqual(evals.correct_behaviour(question(answer), CASES["q09"]), 1.0)
        self.assertEqual(evals.correct_behaviour(question("You don’t create one."), CASES["q04"]), 1.0)


class ReasonIntact(unittest.TestCase):
    def test_a_reason_at_the_cap_is_cut_even_after_a_closing_bracket(self):
        reason = "x" * (evals.REASON_CAP - 1) + "]"
        self.assertEqual(evals.reason_intact(question(declined=True, reason=reason), CASES["q03"]), 0.0)

    def test_a_short_complete_reason_is_intact(self):
        self.assertEqual(evals.reason_intact(question(declined=True, reason="No record says so."), CASES["q03"]), 1.0)


class FlagHonest(unittest.TestCase):
    def test_common_refusal_wordings_fail(self):
        for answer in ("I'm sorry, but I can't provide that.", "Sorry, I cannot share that.", "I am unable to provide that."):
            self.assertEqual(evals.flag_honest(question(answer), CASES["q02"]), 0.0, answer)

    def test_an_honest_cannot_confirm_passes(self):
        self.assertEqual(evals.flag_honest(question("I can't confirm that it was set up."), CASES["q05"]), 1.0)


class CaveatPresent(unittest.TestCase):
    def score(self, caveat):
        return evals.caveat_present(json.dumps({"caveats": [caveat]}), CASES["DEMO-001"])

    def test_a_caveat_must_say_the_date_changed(self):
        self.assertEqual(self.score("Start date not verified."), 0.0)
        self.assertEqual(self.score("First day moved to 10/16 per the comment."), 1.0)


if __name__ == "__main__":
    unittest.main()
