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
        with mock.patch.object(evals, "_PAGES", {}), mock.patch.dict(os.environ, {"CORPUS_PATH": "/no/such/file.jsonl"}):
            self.assertTrue(any(name.startswith("STD-") for name in evals._pages()))


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
