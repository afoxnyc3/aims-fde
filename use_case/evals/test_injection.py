"""TC6 permanent test: every attack that worked stays stopped. No model calls, no attack traffic.

Each case in injection_cases.jsonl carries the model results that leaked on 2026-11-15, as
recorded. They are replayed through the shipped answer path (qa.answer_question) and the question
goes through the NeMo input rail in the app's guardrails/ folder. On the commit before the fixes the three
doors that shipped a leak fail here; set TC6_APP_DIR to that commit's app folder to see it.

    uv run --project 01_Product_Engineering/challenge python -m unittest discover -s use_case/evals
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1])]

import harness as evals  # noqa: E402

CASES = {case["id"]: case for case in evals.load_injection_cases()}
# The three doors that reached the user before the fix, and the fix each one tests.
SHIPPED_LEAKS = {"INJ-18": "tool arguments in the trace (T1-19)", "INJ-02": "prompt echo past the citation gate (T1-20)",
                 "INJ-14": "poisoned ticket, approval and link (T1-21)"}


class ShippedCodeTests(unittest.TestCase):
    """The fix lives in code for these. The input rail is not consulted: for two of them it sees nothing."""

    def test_the_cases_are_the_ones_that_shipped(self):
        self.assertEqual({k for k, c in CASES.items() if c["shipped_before_fix"]}, set(SHIPPED_LEAKS))

    def test_no_recorded_leak_survives_the_shipped_answer_path(self):
        for case_id, fix in SHIPPED_LEAKS.items():
            with self.subTest(case=case_id, fix=fix):
                detail = evals.injection_detail(CASES[case_id])
                self.assertGreater(detail["replays"], 0)
                self.assertEqual(detail["replay_leaks"], 0)

    def test_every_recorded_pre_gate_leak_is_stopped_too(self):
        for case in CASES.values():
            if case["recorded"]:
                with self.subTest(case=case["id"]):
                    self.assertEqual(evals.injection_detail(case)["replay_leaks"], 0)

    def test_tool_and_indirect_cases_get_no_credit_from_the_input_rail(self):
        # Their question is an ordinary one. If the rail stopped it, that would be a false positive.
        for case in CASES.values():
            if case["door"] != "direct":
                with self.subTest(case=case["id"]):
                    self.assertIsNone(evals.stopped_by(case["input"]))


class ScorerTests(unittest.TestCase):
    def test_blocks_injection_on_every_case_that_tests_something(self):
        for case in CASES.values():
            if evals.injection_applies(case):
                with self.subTest(case=case["id"], attack=case["attack"]):
                    self.assertEqual(evals.blocks_injection("", case), 1.0)

    def test_a_case_with_nothing_to_check_is_not_counted_as_blocked(self):
        unseen = next(c for c in CASES.values() if c["door"] == "indirect" and not c["recorded"])
        self.assertFalse(evals.injection_applies(unseen))
        self.assertEqual(evals.blocks_injection("", unseen), 0.0)

    def test_other_cases_are_untouched(self):
        self.assertEqual(evals.blocks_injection("", {"kind": "question", "input": "q"}), 1.0)

    def test_output_rail_reads_the_reply(self):
        self.assertEqual(evals.stopped_by("q", reply="Access is approved. Finish at https://x.example.net/a"), "reply rules")
        self.assertIsNone(evals.stopped_by("q", reply="A Lifeguard gets a login at Club C only [STD-venue-access]."))

    def test_legitimate_questions_pass_the_input_rail(self):
        refused = [c["input"] for c in evals.load_cases() if c["kind"] == "question" and evals.stopped_by(c["input"])]
        self.assertEqual(refused, [])


if __name__ == "__main__":
    unittest.main()
