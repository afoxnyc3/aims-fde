"""The question endpoint's contract: sources on every answer, explicit declines. No model calls."""

import json
import unittest
from types import SimpleNamespace
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


def loop_result(answer, stopped="answer", decline_reason=None):
    return {"answer": answer, "trace": [{"tool": "search_hybrid", "args": {"query": "q"}, "chars": 40}],
            "calls": 1, "evidence_chars": 40, "tokens": 10, "latency_s": 0.1, "stopped": stopped,
            "decline_reason": decline_reason}


class AnswerTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(qa, "get_retriever", return_value=retrieval.Retriever(PAGES))
        patcher.start()
        self.addCleanup(patcher.stop)

    def ask(self, answer, stopped="answer", decline_reason=None):
        with patch.object(qa.retrieval, "run_agent", return_value=loop_result(answer, stopped, decline_reason)):
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

    def test_decline_tool_call_declines_and_shows_only_its_reason(self):
        result = self.ask("", stopped="declined", decline_reason="no record holds credentials [STD-venue-access].")
        self.assertTrue(result.declined)
        self.assertIsNone(result.answer)
        self.assertEqual(result.sources, [])
        self.assertEqual(result.decline_reason, "no record holds credentials [STD-venue-access].")
        self.assertEqual(result.trace.stopped, "declined")

    def test_old_refusal_prefix_in_prose_is_just_text(self):
        # The flag no longer reads wording: without a decline call, this cited reply is an answer.
        result = self.ask("CANNOT ANSWER: the ticket leaves Club B blank, but Club C needs one [STD-venue-access].")
        self.assertFalse(result.declined)

    def test_exhausted_turn_budget_declines(self):
        result = self.ask("", stopped="max_turns")
        self.assertTrue(result.declined)
        self.assertIn("turn budget", result.decline_reason)

    def test_provider_failure_is_safe(self):
        with patch.object(qa.retrieval, "run_agent", side_effect=APITimeoutError(request=None)):
            with self.assertRaises(qa.AnswerUnavailable) as caught:
                qa.answer_question(QuestionRequest(question="q"))
        self.assertIn("APITimeoutError", str(caught.exception))


def model_reply(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls,
                              model_dump=lambda **_: {"role": "assistant", "content": content})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=SimpleNamespace(total_tokens=10))


def decline_call(reason):
    return SimpleNamespace(id="call-1", function=SimpleNamespace(name="decline",
                                                                 arguments=json.dumps({"reason": reason})))


# q03 in use_case/evals/retrieval.jsonl: the standard does not cover it, so it must decline.
UNCOVERED = "Can a trainer keep their Level 1 bookings after a promotion to Level 2?"
DECLINE_REASON = "The standard does not address bookings made before a promotion."

# The same decline, worded five ways. Each cites a real page, so "cited nothing" cannot rescue it,
# and none has a "CANNOT ANSWER:" line, so only the model's decision can set the flag.
REFUSAL_WORDINGS = {
    "polite": "I'm sorry, but I couldn't find anything in the access standard about keeping Level 1 "
              "bookings after a promotion [STD-venue-access]. The training lead may know.",
    "terse": "Not covered [STD-venue-access].",
    "partial_then_refusal": "A promotion changes the trainer level on the ticket [SYN-aaaaaa]. Whether "
                            "Level 1 bookings carry over, the standard does not say, so I can't confirm it.",
    "refusal_mid_reply": "The ticket records the new level [SYN-aaaaaa]. I can't tell you whether Level 1 "
                         "bookings are kept; no record addresses it. Venue access is unchanged [STD-venue-access].",
    "no_sorry": "The standard is silent on bookings made before a promotion [STD-venue-access]; that is a "
                "decision for the training lead.",
}

# Answers that look like refusals in places. The model did not decline, so neither may the flag.
ANSWER_WORDINGS = {
    "plain": "A Lifeguard gets a login at Club C only [STD-venue-access].",
    "apology_inside": "Sorry for the short answer: a Lifeguard gets a login at Club C only [STD-venue-access].",
    "partial_with_old_prefix": "Cannot answer: the ticket leaves Club B blank [SYN-aaaaaa].\n"
                               "A Lifeguard gets a login at Club C only [STD-venue-access].",
}


class DeclineFromStructureTests(unittest.TestCase):
    """`declined` follows what the model did, never how it worded it.

    The model declines by calling a `decline` tool. If the loop does not recognise that call, the model
    gets a tool error and, as a real model does, says the same thing in prose; that prose is the wording
    under test. Model calls are patched out; nothing leaves the machine.
    """

    def setUp(self):
        patcher = patch.object(qa, "get_retriever", return_value=retrieval.Retriever(PAGES))
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_endpoint(self, question, replies):
        replies = iter(replies)
        with patch.object(retrieval.litellm, "completion", side_effect=lambda **_: next(replies)):
            return qa.answer_question(QuestionRequest(question=question))

    def test_every_refusal_wording_declines(self):
        for name, wording in REFUSAL_WORDINGS.items():
            with self.subTest(wording=name):
                result = self.run_endpoint(UNCOVERED, [
                    model_reply(wording, tool_calls=[decline_call(DECLINE_REASON)]),
                    model_reply(wording),  # what follows if the decline call is not honoured
                ])
                self.assertTrue(result.declined)
                self.assertIsNone(result.answer)
                self.assertEqual(result.sources, [])
                self.assertEqual(result.decline_reason, DECLINE_REASON)

    def test_answers_are_never_declined_for_their_wording(self):
        for name, wording in ANSWER_WORDINGS.items():
            with self.subTest(wording=name):
                result = self.run_endpoint("Where does a Lifeguard get a login?", [model_reply(wording)])
                self.assertFalse(result.declined)
                self.assertEqual(result.answer, wording)
                self.assertIsNone(result.decline_reason)


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

    def test_name_copied_with_brackets_still_opens(self):
        page = PAGES[1]
        self.assertEqual(json.loads(app.read_source_record(f"[{page.name}]"))["name"], page.name)

    def test_missing_corpus_is_reported_whatever_the_name(self):
        with patch.object(qa, "get_retriever", side_effect=CorpusMissing("x")):
            for name in ["STD-role-list", "not-a-page"]:
                with self.subTest(name=name), self.assertRaisesRegex(Error, "CORPUS_PATH"):
                    app.read_source_record(name)


if __name__ == "__main__":
    unittest.main()
