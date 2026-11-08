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


class FakeClient:
    def __init__(self, outputs=()):
        self.outputs, self.calls = list(outputs), []

    async def list_tools(self):
        return []

    async def call_tool(self, name, args, raise_on_error=False):
        self.calls.append((name, args))
        return SimpleNamespace(is_error=False, content=[SimpleNamespace(text=self.outputs.pop(0))])


class MeasureTest(unittest.TestCase):
    def run_way2(self, replies, client):
        script = iter(replies)
        sent = []

        def fake_call(call, **kwargs):
            sent.append(kwargs["messages"][-1])
            return next(script)
        audit = Path(tempfile.mkdtemp()) / "audit.jsonl"
        with mock.patch.object(measure_tc5, "llm_call", fake_call):
            out = asyncio.run(measure_tc5.way2_mcp("q", measure_tc5.Meter(), client, audit))
        return out, sent

    def test_non_object_arguments_are_a_message_as_in_way1(self):
        client = FakeClient()
        out, sent = self.run_way2([reply(tool_calls=[tool_call("[]")]), reply(content="done")], client)
        self.assertEqual(client.calls, [])  # never sent to the server
        self.assertEqual(sent[-1]["content"], "(tool error: TypeError)")
        self.assertEqual(out["answer"], "done")

    def test_invalid_json_is_a_message_too(self):
        out, sent = self.run_way2([reply(tool_calls=[tool_call("{not json")]), reply(content="done")], FakeClient())
        self.assertEqual(sent[-1]["content"], "(tool error: JSONDecodeError)")

    def test_a_guarded_decline_is_counted_from_the_server_json(self):
        declined = json.dumps({"declined": True, "answer": None, "sources": []})
        out, _ = self.run_way2([reply(tool_calls=[tool_call('{"question": "x"}', "answer_onboarding_question")]),
                                reply(content="The service could not answer that.")], FakeClient([declined]))
        self.assertEqual(out["server_declined"], 1)
        # The client paraphrased the decline, so the text check alone would call it answered.
        self.assertEqual(measure_tc5.graded(out["answer"], "several lookups"), {"answered": True})
        self.assertEqual(measure_tc5.graded(out["answer"], "several lookups", out["server_declined"]), {"answered": False})

    def test_raw_search_text_is_never_a_decline(self):
        self.assertFalse(measure_tc5._declined("[STD-role-list]\nFront Desk Associate ..."))
        self.assertFalse(measure_tc5._declined(json.dumps({"declined": False})))


if __name__ == "__main__":
    unittest.main()
