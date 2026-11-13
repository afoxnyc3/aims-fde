"""The retrieval measurement's scorer. No model, no corpus, no embedding calls."""

import unittest

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


if __name__ == "__main__":
    unittest.main()
