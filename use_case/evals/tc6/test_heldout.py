"""The held-out legitimate questions and the direct attacks through the input rail (rules, no model)."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[2])]

import harness as evals  # noqa: E402
import heldout_pass  # noqa: E402


class HeldOutLegitTests(unittest.TestCase):
    def test_the_set_is_24_questions_and_at_least_8_use_the_risky_vocabulary(self):
        rows = evals.load_jsonl(HERE / "heldout_legit.jsonl")
        self.assertEqual(len({row["question"] for row in rows}), 24)
        self.assertGreaterEqual(sum(row["vocabulary"] for row in rows), 8)

    def test_the_input_rail_refuses_no_held_out_legitimate_question(self):
        for row in evals.load_jsonl(HERE / "heldout_legit.jsonl"):
            with self.subTest(id=row["id"]):
                self.assertIsNone(evals.stopped_by(row["question"]))

    def test_the_input_rail_still_stops_every_direct_attack(self):
        attacks = heldout_pass.direct_attacks()
        self.assertEqual(len(attacks), 12)
        for label, text in attacks:
            with self.subTest(attack=label):
                self.assertEqual(evals.stopped_by(text), "prompt probe rules")


if __name__ == "__main__":
    unittest.main()
