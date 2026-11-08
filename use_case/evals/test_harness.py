"""Pins what the scorers must catch and must not. No model calls.

    uv run --project 01_Product_Engineering/challenge python -m unittest discover -s use_case/evals
"""

import copy
import json
import os
import sys
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
        with mock.patch.dict(os.environ, {"ONBOARDING_STANDARD": "/private/std.yaml"}):
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
