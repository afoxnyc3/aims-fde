"""Pins what the scorers must catch and must not. No model calls.

    uv run --project 01_Product_Engineering/challenge python -m unittest discover -s use_case/evals
"""

import copy
import json
import sys
import unittest
from pathlib import Path

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
