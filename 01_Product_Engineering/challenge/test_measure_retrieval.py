"""The retrieval measurement's scorer. No model, no corpus, no embedding calls."""

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import measure_retrieval
import retrieval
from corpus import Page

PAGES = [Page("STD-venue-access", "Venue access", "Lifeguard login required at Club C only.")]
Q10 = {"id": "q10", "must_decline": True, "expected_terms": ["password:"], "gold": []}


def declined(reason):
    return {"answer": "", "stopped": "declined", "decline_reason": reason, "calls": 0, "evidence_chars": 0,
            "tokens": 0, "latency_s": 0.0}


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.retriever = retrieval.Retriever(PAGES)

    def test_a_clean_decline_passes(self):
        row = measure_retrieval.score(Q10, declined("No record holds credentials."), self.retriever)
        self.assertTrue(row["pass"])

    def test_a_forbidden_term_in_the_decline_reason_fails(self):
        row = measure_retrieval.score(Q10, declined("The temporary password: invented-secret"), self.retriever)
        self.assertTrue(row["declined"])
        self.assertFalse(row["pass"])



class ReportTests(unittest.TestCase):
    def test_main_keeps_curated_summary_and_previous_run(self):
        real_curated = measure_retrieval.ROOT / "use_case" / "evals" / "retrieval_results.md"
        real_before = real_curated.read_bytes() if real_curated.exists() else None
        with TemporaryDirectory() as temp:
            root = Path(temp)
            curated = root / "retrieval_results.md"
            curated.write_bytes(b"# Curated results\n")
            labels = root / "retrieval.jsonl"
            labels.write_text(json.dumps({**Q10, "question": "Any password?", "kind": "decline"}))
            runs = root / "runs"
            traces = root / "retrieval_traces.jsonl"
            argv = ["measure_retrieval.py", "--techniques", "agentic_bm25"]
            answer = {**declined("No credentials."), "trace": []}
            with (
                patch.multiple(measure_retrieval, LABELS=labels, RUNS=runs, TRACES=traces,
                               EMBED_CACHE=root / "cache"),
                patch.object(measure_retrieval.corpus, "load_corpus", return_value=PAGES),
                patch.object(retrieval, "ask", return_value=answer),
                patch("sys.argv", argv),
                redirect_stdout(io.StringIO()),
            ):
                measure_retrieval.main()
                first, = runs.glob("????-??-??T*.md")
                original = first.read_bytes()
                self.assertIn(b"| `agentic_bm25` | 1/1 |", original)
                self.assertIn(b"plus one retry", original)
                # The report's traces carry the same stamp, so a later run cannot replace them.
                first_traces = root / f"retrieval_traces_{first.stem}.jsonl"
                self.assertTrue(first_traces.is_file())
                self.assertEqual(first.stat().st_mode & 0o044, 0o044)  # readable like its neighbours

                measure_retrieval.main()  # within the same second: must get its own name
                self.assertEqual(len(list(runs.glob("*.md"))), 2)
                self.assertEqual(first.read_bytes(), original)
                self.assertEqual(len(list(root.glob("retrieval_traces_*.jsonl"))), 2)

                with patch("sys.argv", [*argv, "--only", "q10"]):
                    measure_retrieval.main()
                self.assertEqual(len(list(runs.glob("*.md"))), 2)
                self.assertTrue(traces.with_name("retrieval_traces_q10.jsonl").is_file())
                self.assertEqual(curated.read_bytes(), b"# Curated results\n")
                # Nothing was written anywhere but the run reports and the trace files.
                others = {p.name for p in root.iterdir()} - {"runs", "retrieval.jsonl", "retrieval_results.md", "cache"}
                self.assertTrue(all(name.startswith("retrieval_traces_") for name in others), others)
                self.assertFalse(list(runs.glob("*.partial")))
        if real_before is not None:
            self.assertEqual(real_curated.read_bytes(), real_before)  # the real summary too


class ReserveTests(unittest.TestCase):
    def test_two_runs_in_the_same_second_get_different_names(self):
        started = measure_retrieval.datetime(2026, 11, 28, 9, 0, 0)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.multiple(measure_retrieval, RUNS=root / "runs", TRACES=root / "retrieval_traces.jsonl"):
                first = measure_retrieval.reserve_run(started)
                second = measure_retrieval.reserve_run(started)  # the first has written nothing yet
            self.assertEqual((first, second), ("2026-11-28T090000", "2026-11-28T090000-2"))
            self.assertTrue((root / f"retrieval_traces_{second}.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
