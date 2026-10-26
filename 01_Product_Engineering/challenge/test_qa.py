"""The question endpoint's contract: sources on every answer, explicit declines. No model calls."""

import json
import unittest
from unittest.mock import patch

from gradio import Error
from openai import APITimeoutError
from pydantic import ValidationError

import app
import qa
import retrieval
from corpus import CorpusMissing, Page
from qa_schema import QuestionAnswer, QuestionRequest

PAGES = [
    Page("STD-venue-access", "Venue access", "Lifeguard login required at Club C only."),
    Page("SYN-aaaaaa", "New hire: Example Person - Lifeguard", "Lifeguard at Club B."),
]


def loop_result(answer, stopped="answer"):
    return {"answer": answer, "trace": [{"tool": "search_hybrid", "args": {"query": "q"}, "chars": 40}],
            "calls": 1, "evidence_chars": 40, "tokens": 10, "latency_s": 0.1, "stopped": stopped}


class AnswerTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(qa, "get_retriever", return_value=retrieval.Retriever(PAGES))
        patcher.start()
        self.addCleanup(patcher.stop)

    def ask(self, answer, stopped="answer"):
        with patch.object(qa.retrieval, "run_agent", return_value=loop_result(answer, stopped)):
            return qa.answer_question(QuestionRequest(question="Where does a Lifeguard get a login?"))

    def test_answer_carries_only_real_sources(self):
        result = self.ask("Club C only [STD-venue-access]; see also [SYN-ffffff].")
        self.assertFalse(result.declined)
        self.assertEqual(result.sources, ["STD-venue-access"])
        self.assertEqual(result.dropped_citations, ["SYN-ffffff"])
        self.assertEqual(result.trace.steps[0].tool, "search_hybrid")

    def test_uncited_answer_is_declined_and_its_text_never_returned(self):
        result = self.ask("Probably Club C, per [SYN-ffffff].")
        self.assertTrue(result.declined)
        self.assertIsNone(result.answer)
        self.assertEqual(result.sources, [])
        self.assertNotIn("Club C", result.decline_reason)

    def test_explicit_refusal_declines_even_when_it_cites_pages(self):
        result = self.ask("CANNOT ANSWER: no record holds credentials [STD-venue-access].\nMore text.")
        self.assertTrue(result.declined)
        self.assertEqual(result.sources, [])
        self.assertEqual(result.decline_reason, "no record holds credentials [STD-venue-access].")

    def test_bare_or_wrapped_refusals_decline_cleanly(self):
        for text in ("CANNOT ANSWER:", "**CANNOT ANSWER:** nothing on passwords",
                     "I searched [STD-venue-access].\nCANNOT ANSWER: no record holds credentials"):
            result = self.ask(text)
            self.assertTrue(result.declined, text)
            self.assertEqual(result.sources, [], text)
            self.assertTrue(result.decline_reason, text)

    def test_exhausted_turn_budget_declines(self):
        result = self.ask("", stopped="max_turns")
        self.assertTrue(result.declined)
        self.assertIn("turn budget", result.decline_reason)

    def test_provider_failure_is_safe(self):
        with patch.object(qa.retrieval, "run_agent", side_effect=APITimeoutError(request=None)):
            with self.assertRaises(qa.AnswerUnavailable) as caught:
                qa.answer_question(QuestionRequest(question="q"))
        self.assertIn("APITimeoutError", str(caught.exception))


class ContractTests(unittest.TestCase):
    def test_answer_without_sources_is_invalid(self):
        with self.assertRaises(ValidationError):
            QuestionAnswer(question="q", declined=False, answer="Club C", sources=[],
                           trace=dict(technique="t", model="m", steps=[], evidence_chars=0,
                                      latency_s=0, stopped="answer"))

    def test_endpoint_rejects_bad_json_and_missing_corpus(self):
        with self.assertRaisesRegex(Error, "Invalid question"):
            app.answer_onboarding_question(json.dumps({"question": ""}))
        with patch.object(app, "answer_question", side_effect=CorpusMissing("x")):
            with self.assertRaisesRegex(Error, "not mounted"):
                app.answer_onboarding_question(json.dumps({"question": "q"}))


if __name__ == "__main__":
    unittest.main()


class SourceRecordTests(unittest.TestCase):
    """read_source_record lets a reader open a cited record; nothing else."""

    def setUp(self):
        patcher = patch.object(qa, "get_retriever", return_value=retrieval.Retriever(PAGES))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cited_record_is_returned_whole(self):
        page = PAGES[0]
        record = json.loads(app.read_source_record(page.name))
        self.assertEqual(record, {"name": page.name, "title": page.title, "text": page.text})

    def test_unknown_or_malformed_names_are_errors_that_do_not_echo_input(self):
        for name in ["SYN-ffffff", "../etc/passwd", "", "STD-role-list; drop"]:
            with self.subTest(name=name), self.assertRaises(Error) as caught:
                app.read_source_record(name)
            if name:
                self.assertNotIn(name, str(caught.exception))

    def test_missing_corpus_is_a_clear_error(self):
        with patch.object(qa, "get_retriever", side_effect=CorpusMissing("x")):
            with self.assertRaisesRegex(Error, "CORPUS_PATH"):
                app.read_source_record("STD-role-list")
