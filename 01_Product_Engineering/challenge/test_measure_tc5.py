"""Offline tests for the TC5 measurement harness: no model, no server process, no corpus.

Runs under the challenge's own test command: python -m unittest test_measure_tc5
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import measure_tc5


def reply(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls,
                              model_dump=lambda **kw: {"role": "assistant", "content": content})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=SimpleNamespace(total_tokens=10))


def tool_call(arguments, name="search_hybrid"):
    return SimpleNamespace(id="t1", function=SimpleNamespace(name=name, arguments=arguments))


ANSWER_DONE = reply(tool_calls=[tool_call('{"text": "done"}', "answer")])


class FakeClient:
    def __init__(self, outputs=()):
        self.outputs, self.calls = list(outputs), []

    async def list_tools(self):
        return []

    async def call_tool(self, name, args, raise_on_error=False):
        self.calls.append((name, args))
        return SimpleNamespace(is_error=False, content=[SimpleNamespace(text=self.outputs.pop(0))])


class MeasureTest(unittest.TestCase):
    def run_way2(self, replies, client, final_tools=True):
        script = iter(replies)
        sent = []

        def fake_call(call, **kwargs):
            sent.append(kwargs["messages"][-1])
            return next(script)
        audit = Path(tempfile.mkdtemp()) / "audit.jsonl"
        with mock.patch.object(measure_tc5, "llm_call", fake_call):
            out = asyncio.run(measure_tc5.way2_mcp("q", measure_tc5.Meter(), client, audit,
                                                   final_tools=final_tools))
        return out, sent

    def test_non_object_arguments_are_a_message_as_in_way1(self):
        client = FakeClient()
        out, sent = self.run_way2([reply(tool_calls=[tool_call("[]")]), ANSWER_DONE], client)
        self.assertEqual(client.calls, [])  # never sent to the server
        self.assertEqual(sent[-1]["content"], "(tool error: TypeError)")
        self.assertEqual(out["answer"], "done")

    def test_invalid_json_is_a_message_too(self):
        out, sent = self.run_way2([reply(tool_calls=[tool_call("{not json")]), ANSWER_DONE], FakeClient())
        self.assertEqual(sent[-1]["content"], "(tool error: JSONDecodeError)")

    def test_a_guarded_decline_is_counted_from_the_server_json(self):
        declined = json.dumps({"declined": True, "answer": None, "sources": []})
        out, _ = self.run_way2([reply(tool_calls=[tool_call('{"question": "x"}', "answer_onboarding_question")]),
                                reply(content="The service could not answer that.")], FakeClient([declined]),
                               final_tools=False)  # 2b: an outside client, server tools only
        self.assertEqual(out["server_declined"], 1)
        # The client paraphrased the decline, so the text check alone would call it answered.
        self.assertEqual(measure_tc5.graded(out["answer"], "several lookups"), {"answered": True})
        self.assertEqual(measure_tc5.graded(out["answer"], "several lookups", out["server_declined"]), {"answered": False})

    def test_way2_reads_declines_from_the_final_call_not_the_text(self):
        decline = reply(content="Happy to help!", tool_calls=[tool_call('{"reason": "not covered"}', "decline")])
        out, _ = self.run_way2([decline], FakeClient())
        self.assertEqual((out["answer"], out["declined"]), ("", True))
        self.assertEqual(measure_tc5.graded(out["answer"], "one lookup", 0, out["declined"]), {"answered": False,
                                                                                               "role_named": False})
        out, _ = self.run_way2([reply(content="Front Desk Associate."), reply(content="Still prose.")],
                               FakeClient())  # prose, retried, prose: no decision
        self.assertTrue(out["declined"])
        out, _ = self.run_way2([reply(content="Front Desk Associate."), ANSWER_DONE], FakeClient())
        self.assertEqual((out["answer"], out["declined"]), ("done", False))  # the retry recovered it

    def test_first_turn_count_excludes_answer_and_decline(self):
        meter = measure_tc5.Meter()
        turn = reply(tool_calls=[tool_call("{}"), tool_call("{}"), tool_call("{}", "decline")])
        meter.wrap(lambda call, **_: turn)(measure_tc5.litellm.completion)
        self.assertEqual(meter.first_turn_tool_calls, 2)

    def test_raw_search_text_is_never_a_decline(self):
        self.assertFalse(measure_tc5._declined("[STD-role-list]\nFront Desk Associate ..."))
        self.assertFalse(measure_tc5._declined(json.dumps({"declined": False})))


if __name__ == "__main__":
    unittest.main()
