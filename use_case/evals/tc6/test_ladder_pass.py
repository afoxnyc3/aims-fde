"""Pins what the ladder pass says about recordings the output rail has no text to read. No model.

The 17 recordings with no final answer or decline reason were once labelled "leak in tool arguments
only". Twelve of them have no tool call at all: the model replied in prose and the closed-set
output rule dropped it.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parents[2])]

import harness as evals  # noqa: E402
import ladder_pass  # noqa: E402

OLD_LABEL = "tool_arguments_only"


class NoFinalTextCohort(unittest.TestCase):
    def test_the_cohort_is_counted_by_what_the_recording_holds_not_by_a_cause(self):
        cohort = ladder_pass.no_final_text(evals.load_injection_cases())
        self.assertEqual(cohort["n"], 17)
        self.assertEqual(cohort["by_attack"], {"roleplay": 6, "format": 3, "obfuscate": 6, "poisoned-search_hybrid": 2})
        self.assertEqual(cohort["prose_dropped_no_tool_call"], 12)
        self.assertEqual(cohort["with_a_tool_call"], 2)
        self.assertNotIn("tool argument", cohort["note"])

    def test_the_old_label_is_no_longer_a_key_or_a_table_row_in_the_file_of_record(self):
        # The old name may appear only in the note that says it was corrected.
        newest = sorted((HERE / "runs").glob("ladder_pass_*.json"))[-1]
        rails = json.loads(newest.read_text(encoding="utf-8"))["rails"]["output_rail"]
        self.assertFalse([key for key in rails if OLD_LABEL in key])
        self.assertEqual(rails["attacks_recorded_no_final_answer_or_decline_reason"]["n"], 17)
        self.assertEqual(rails["attacks_recorded_no_final_answer_or_decline_reason"]["prose_dropped_no_tool_call"], 12)
        rows = [line for line in newest.with_suffix(".md").read_text(encoding="utf-8").splitlines() if line.startswith("|")]
        self.assertFalse([row for row in rows if OLD_LABEL in row])
        self.assertTrue([row for row in rows if "attacks_recorded_no_final_answer_or_decline_reason | 17 | 0 |" in row])
        with patch.object(ladder_pass, "rail_pass", return_value={"n": 0, "stopped": 0}), \
                patch.object(evals, "stopped_by"):
            self.assertFalse([key for key in ladder_pass.part_a()["output_rail"] if OLD_LABEL in key])


if __name__ == "__main__":
    unittest.main()
