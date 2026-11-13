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
from test_retrieval import reply, tool_call

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

    def test_unstructured_reply_declines_and_its_text_is_never_returned(self):
        result = self.ask("", stopped="unstructured")
        self.assertTrue(result.declined)
        self.assertIsNone(result.answer)
        self.assertIn("without choosing", result.decline_reason)

    def test_exhausted_turn_budget_declines(self):
        result = self.ask("", stopped="max_turns")
        self.assertTrue(result.declined)
        self.assertIn("turn budget", result.decline_reason)

    def test_provider_failure_is_safe(self):
        with patch.object(qa.retrieval, "run_agent", side_effect=APITimeoutError(request=None)):
            with self.assertRaises(qa.AnswerUnavailable) as caught:
                qa.answer_question(QuestionRequest(question="q"))
        self.assertIn("APITimeoutError", str(caught.exception))


def decline_call(reason):
    return tool_call("decline", json.dumps({"reason": reason}))


def answer_call(text):
    return tool_call("answer", json.dumps({"text": text}))


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
    """`declined` follows the model's final call, never how its text is worded.

    The model must end in an `answer` or a `decline` call. Each scripted turn carries the wording as
    its prose; if the loop does not honour the call, the model gets a tool error and, as a real model
    does, says the same thing in prose, which is then all the code has to go on. Model calls are
    patched out; nothing leaves the machine.
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
                result = self.run_endpoint(UNCOVERED, [reply(wording, [decline_call(DECLINE_REASON)]),
                                                       reply(wording)])
                self.assertTrue(result.declined)
                self.assertIsNone(result.answer)
                self.assertEqual(result.sources, [])
                self.assertEqual(result.decline_reason, DECLINE_REASON)

    def test_answers_are_never_declined_for_their_wording(self):
        for name, wording in ANSWER_WORDINGS.items():
            with self.subTest(wording=name):
                result = self.run_endpoint("Where does a Lifeguard get a login?",
                                           [reply(None, [answer_call(wording)]), reply(wording)])
                self.assertFalse(result.declined)
                self.assertEqual(result.answer, wording)
                self.assertIsNone(result.decline_reason)

    def test_prose_with_no_final_call_declines_whatever_it_says(self):
        # A model that skips both final tools made no decision the code can read. Every
        # wording, refusal or answer, fails closed, and its text is never passed on.
        for name, wording in {**REFUSAL_WORDINGS, **ANSWER_WORDINGS}.items():
            with self.subTest(wording=name):
                result = self.run_endpoint(UNCOVERED, [reply(wording), reply(wording)])  # prose, retried, prose
                self.assertTrue(result.declined)
                self.assertIsNone(result.answer)
                self.assertIn("without choosing", result.decline_reason)

    def test_invented_ids_in_a_decline_reason_are_reported(self):
        result = self.run_endpoint(UNCOVERED, [reply(None, [decline_call("See [SYN-ffffff] and [STD-venue-access].")])])
        self.assertTrue(result.declined)
        self.assertEqual(result.dropped_citations, ["SYN-ffffff"])


PROSE = "A Lifeguard gets a login at Club C only [STD-venue-access]."


class RepairTurnTests(unittest.TestCase):
    """A prose reply gets one retry that offers only answer and decline. The flag still comes from a call.

    Model calls are patched out; `calls` records what each one was sent.
    """

    def setUp(self):
        patcher = patch.object(qa, "get_retriever", return_value=retrieval.Retriever(PAGES))
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_endpoint(self, replies):
        replies, self.calls = iter(replies), []

        def completion(**kwargs):
            self.calls.append(kwargs)
            return next(replies)

        with patch.object(retrieval.litellm, "completion", side_effect=completion):
            return qa.answer_question(QuestionRequest(question="Where does a Lifeguard get a login?"))

    def assert_retried_with_final_tools_only(self):
        self.assertEqual(len(self.calls), 2)
        retry = self.calls[1]
        self.assertEqual([t["function"]["name"] for t in retry["tools"]], ["answer", "decline"])
        self.assertEqual(retry["messages"][-2], {"role": "assistant", "content": PROSE})
        self.assertEqual(retry["messages"][-1], {"role": "user", "content": retrieval.REPAIR_PROMPT})

    def test_prose_then_answer_is_answered(self):
        result = self.run_endpoint([reply(PROSE), reply(None, [answer_call(PROSE)])])
        self.assert_retried_with_final_tools_only()
        self.assertFalse(result.declined)
        self.assertEqual(result.answer, PROSE)
        self.assertTrue(result.trace.retried)

    def test_prose_then_decline_is_declined(self):
        result = self.run_endpoint([reply(PROSE), reply(None, [decline_call(DECLINE_REASON)])])
        self.assert_retried_with_final_tools_only()
        self.assertTrue(result.declined)
        self.assertEqual(result.decline_reason, DECLINE_REASON)
        self.assertTrue(result.trace.retried)

    def test_prose_then_prose_declines_and_no_text_leaks(self):
        result = self.run_endpoint([reply(PROSE), reply("Club C, as I said [STD-venue-access].")])
        self.assert_retried_with_final_tools_only()
        self.assertTrue(result.declined)
        self.assertIsNone(result.answer)
        self.assertEqual(result.sources, [])
        dumped = result.model_dump_json()
        self.assertNotIn("Club C", dumped)
        self.assertEqual(result.trace.stopped, "unstructured")

    def test_a_search_call_in_the_retry_is_not_a_final_call(self):
        search = tool_call("search_hybrid", '{"query": "q"}')
        result = self.run_endpoint([reply(PROSE), reply(None, [search])])
        self.assertTrue(result.declined)
        self.assertEqual(result.trace.stopped, "unstructured")

    def test_a_correct_first_call_is_never_retried(self):
        for first in (reply(None, [answer_call(PROSE)]), reply(None, [decline_call(DECLINE_REASON)])):
            with self.subTest(first=first.choices[0].message.tool_calls[0].function.name):
                result = self.run_endpoint([first])
                self.assertEqual(len(self.calls), 1)
                self.assertFalse(result.trace.retried)


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
