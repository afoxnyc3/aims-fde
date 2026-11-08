"""Offline tests for the TC5 MCP server: no model, no embeddings, no corpus.

Runs under the challenge's own test command: python -m unittest test_mcp_server
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx
from fastmcp import Client
from openai import APIError

import mcp_server


class FakeRetriever:
    def __init__(self):
        self.queries = []

    def search_hybrid(self, query, k=4):
        self.queries.append((query, k))
        return f"[STD-role-list]\nresult for {query} (k={k})"


class Boom:
    def __init__(self, exc):
        self.exc = exc

    def search_hybrid(self, query, k=4):
        raise self.exc


def call(server, name, args):
    async def go():
        async with Client(server) as client:
            return await client.call_tool(name, args, raise_on_error=False)
    return asyncio.run(go())


def text(result):
    return " ".join(block.text for block in result.content)


class McpServerTest(unittest.TestCase):
    def setUp(self):
        self.saved = mcp_server._retriever
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "audit.jsonl"
        self.fake = FakeRetriever()
        mcp_server._retriever = self.fake
        self.audit = mcp_server.AuditCounter(str(self.log))
        self.server = mcp_server.build_server(self.audit, toolset={"search"})

    def tearDown(self):
        mcp_server._retriever = self.saved

    def log_lines(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_lists_only_the_capability(self):
        async def go():
            async with Client(self.server) as client:
                return [tool.name for tool in await client.list_tools()]
        self.assertEqual(asyncio.run(go()), ["search_hybrid"])

    def test_call_reaches_capability_and_is_counted_server_side(self):
        result = call(self.server, "search_hybrid", {"query": "lifeguard", "k": 2})
        self.assertFalse(result.is_error)
        self.assertIn("result for lifeguard (k=2)", text(result))
        self.assertEqual(self.fake.queries, [("lifeguard", 2)])
        self.assertEqual(self.audit.calls, {"search_hybrid": 1})
        [line] = self.log_lines()
        self.assertEqual(line["arg_keys"], ["k", "query"])
        self.assertGreater(line["response_bytes"], 0)
        self.assertIsNone(line["error"])
        self.assertEqual((line["server_model_tokens"], line["server_model_turns"]), (0, 0))
        self.assertNotIn("lifeguard", self.log.read_text())  # shape only, never content

    def test_unknown_tool_is_a_message_naming_real_tools(self):
        result = call(self.server, "lookup_team", {"query": "x"})
        self.assertTrue(result.is_error)
        self.assertEqual(text(result), "Unknown tool 'lookup_team'. Available tools: search_hybrid.")
        self.assertEqual(self.fake.queries, [])
        self.assertEqual(self.audit.calls, {})  # rejected before the capability: logged, not counted
        [line] = self.log_lines()
        self.assertEqual((line["error"], line["reached"]), ("NotFoundError", False))

    def test_malformed_arguments_are_a_message_without_echoing_input(self):
        result = call(self.server, "search_hybrid", {"query": "SECRET ticket text", "k": "lots"})
        self.assertTrue(result.is_error)
        self.assertTrue(text(result).startswith("Bad arguments for 'search_hybrid': k:"))
        self.assertNotIn("SECRET", text(result))
        self.assertNotIn("lots", text(result))
        self.assertEqual(self.fake.queries, [])
        self.assertEqual(self.audit.calls, {})
        [line] = self.log_lines()
        self.assertEqual((line["error"], line["reached"]), ("ValidationError", False))

    def test_unexpected_failure_leaks_no_detail_and_is_still_counted(self):
        mcp_server._retriever = Boom(RuntimeError("internal detail SECRET"))
        result = call(self.server, "search_hybrid", {"query": "SECRET"})
        self.assertTrue(result.is_error)
        self.assertNotIn("internal detail", text(result))
        self.assertNotIn("SECRET", text(result))
        # B: a call that raises still counts and still logs, with its error class
        self.assertEqual(self.audit.calls, {"search_hybrid": 1})
        [line] = self.log_lines()
        self.assertEqual(line["error"], "RuntimeError")
        self.assertNotIn("SECRET", self.log.read_text())

    def test_upstream_outage_is_a_fixed_marker_not_a_declinable_error(self):
        # A: same contract as Way 1, whose run_agent re-raises APIError
        mcp_server._retriever = Boom(APIError("down", httpx.Request("GET", "http://x"), body=None))
        result = call(self.server, "search_hybrid", {"query": "x"})
        self.assertTrue(result.is_error)
        self.assertEqual(text(result), mcp_server.UPSTREAM_UNAVAILABLE)
        [line] = self.log_lines()
        self.assertEqual(line["error"], "APIError")


class GuardedToolTest(unittest.TestCase):
    """The shipped default: only the guarded endpoint, never raw records."""

    def setUp(self):
        self.saved = mcp_server.qa.answer_question
        self.server = mcp_server.build_server(mcp_server.AuditCounter(None))

    def tearDown(self):
        mcp_server.qa.answer_question = self.saved

    def test_default_toolset_is_the_guarded_endpoint_only(self):
        async def go():
            async with Client(self.server) as client:
                return [tool.name for tool in await client.list_tools()]
        self.assertEqual(asyncio.run(go()), ["answer_onboarding_question"])

    def test_returns_answer_and_sources_without_the_trace(self):
        from qa_schema import QuestionAnswer
        fields = QuestionAnswer.model_fields

        def fake(request):
            values = {name: None for name in fields}
            values.update(answer="Use Front Desk Associate [STD-role-list].", sources=["STD-role-list"])
            return QuestionAnswer.model_construct(**values)
        mcp_server.qa.answer_question = fake
        result = call(self.server, "answer_onboarding_question", {"question": "Hospitality Associate Level 1?"})
        self.assertFalse(result.is_error)
        body = json.loads(text(result))
        self.assertEqual(body["sources"], ["STD-role-list"])
        self.assertNotIn("trace", body)

    def test_service_outage_is_the_fixed_marker(self):
        def down(request):
            raise mcp_server.qa.AnswerUnavailable("the model service failed (APIError)")
        mcp_server.qa.answer_question = down
        result = call(self.server, "answer_onboarding_question", {"question": "x"})
        self.assertTrue(result.is_error)
        self.assertEqual(text(result), mcp_server.UPSTREAM_UNAVAILABLE)

    def test_empty_blank_or_oversized_question_is_a_clear_message(self):
        mcp_server.qa.answer_question = lambda request: self.fail("must not reach the capability")
        for question in ["", "   ", "x" * 2001]:
            result = call(self.server, "answer_onboarding_question", {"question": question})
            self.assertTrue(result.is_error)
            self.assertTrue(text(result).startswith("Bad arguments for 'answer_onboarding_question': question:"),
                            text(result))
            self.assertNotIn("xxxx", text(result))


class ToolsetTest(unittest.TestCase):
    def test_unknown_toolset_refuses_to_start(self):
        with self.assertRaises(ValueError):
            mcp_server.build_server(mcp_server.AuditCounter(None), toolset={"serach"})

    def test_importing_does_not_patch_the_model_call(self):
        import llm
        self.assertIsNot(llm.call_with_retry, mcp_server._counting_call_with_retry)


if __name__ == "__main__":
    unittest.main()
