"""Corpus construction and label integrity. No model calls."""

import json
import unittest
from pathlib import Path

import corpus

LABELS = Path(__file__).parent.parent.parent / "use_case" / "evals" / "retrieval.jsonl"


def synthetic_row(row_id="exact|new_hire|clean|member_plus_staff_login#0", **ticket):
    return {
        "row_id": row_id,
        "verified": True,
        "expected_status": "recommended",
        "expected_reason": None,
        "expected_caveat": None,
        "expected_proposal": {"standard_role": "Lifeguard", "club": "Club C", "login_required": True},
        "ticket": {
            "request_type": "New Hire Onboarding",
            "summary": "New hire: Example Person - Lifeguard",
            "fields": {"location": "Club B", "job_title": "Lifeguard"},
            "form": {"login_required": "YES", "previous_location": ""},
            "notes": "Starts soon.",
            "comments": [{"author_role": "requester", "timestamp": "2026-10-08T13:20:00", "body": "Club C instead."}],
            **ticket,
        },
    }


class CorpusTests(unittest.TestCase):
    def test_ticket_names_are_stable_and_hide_the_axes(self):
        row_id = "outside_standard|returning_or_moving|clean|beyond_template#0"
        self.assertEqual(corpus.ticket_page_name(row_id), corpus.ticket_page_name(row_id))
        self.assertRegex(corpus.ticket_page_name(row_id), r"^SYN-[0-9a-f]{6}$")
        self.assertNotIn("outside_standard", corpus.render_ticket(synthetic_row(row_id)).text)

    def test_ticket_page_has_every_heading_and_the_comment(self):
        page = corpus.render_ticket(synthetic_row())
        for heading in ("## Summary", "## Form fields", "## Notes", "## Comments", "## Outcome (draft rule)"):
            self.assertIn(heading, page.text)
        self.assertIn("(requester): Club C instead.", page.text)
        self.assertNotIn("previous_location", page.text)  # blank fields are left out

    def test_standard_splits_into_three_named_pages(self):
        names = [page.name for page in corpus.load_standard_pages()]
        self.assertEqual(names, ["STD-role-list", "STD-venue-access", "STD-status-rule"])

    def test_missing_corpus_file_raises(self):
        with self.assertRaises(corpus.CorpusMissing):
            corpus.load_ticket_pages(Path("/nonexistent/synthetic_v1.jsonl"))


@unittest.skipUnless(corpus.DEFAULT_CORPUS_PATH.exists(), "synthetic_v1.jsonl is local-only")
class LabelTests(unittest.TestCase):
    """Runs only where the gitignored data file is present."""

    def test_every_gold_id_is_a_page(self):
        names = {page.name for page in corpus.load_corpus(corpus.DEFAULT_CORPUS_PATH)}
        labels = [json.loads(line) for line in LABELS.read_text().splitlines() if line.strip()]
        self.assertGreaterEqual(len(labels), 10)
        for label in labels:
            self.assertTrue(set(label["gold"]) <= names, label["id"])
        self.assertTrue(any(label["kind"] == "decline" for label in labels))


if __name__ == "__main__":
    unittest.main()
