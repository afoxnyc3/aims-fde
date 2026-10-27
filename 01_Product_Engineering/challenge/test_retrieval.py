"""Retrieval mechanics. Model and embedding calls are patched out; nothing leaves the machine."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from openai import APITimeoutError

import retrieval
from corpus import Page

PAGES = [
    Page("STD-venue-access", "Venue access", "Lifeguard login required at Club C only."),
    Page("STD-role-list", "Role list", "Cafe Associate: no staff login at any club."),
    Page("SYN-aaaaaa", "New hire: Example Person - Lifeguard", "Lifeguard at Club B. Status: recommended"),
]


def tool_call(name, arguments="{}", call_id="call-1"):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def reply(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls,
                              model_dump=lambda **_: {"role": "assistant", "content": content})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=SimpleNamespace(total_tokens=10))


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.retriever = retrieval.Retriever(PAGES)

    def test_rrf_rewards_agreement_over_one_high_rank(self):
        fused = dict(retrieval.reciprocal_rank_fusion([["a", "b"], ["b", "c"]], k=60))
        self.assertAlmostEqual(fused["b"], 1 / 62 + 1 / 61)
        self.assertEqual(max(fused, key=fused.get), "b")

    def test_bm25_finds_the_exact_title(self):
        self.assertEqual(self.retriever.bm25_ranked("Cafe Associate", 1)[0][0], "STD-role-list")

    def test_grep_survives_an_invalid_regex(self):
        # "(" alone is an invalid regex; it falls back to a literal search instead of raising.
        self.assertEqual(self.retriever.grep_pages("Club C ("), "(no matches)")
        self.assertIn("STD-venue-access:1:", self.retriever.grep_pages("Club C"))

    def test_grep_is_literal_so_a_backtracking_pattern_is_harmless(self):
        slow = retrieval.Retriever([Page("SYN-bbbbbb", "t", "a" * 5000 + "!")])
        self.assertEqual(slow.grep_pages("(a+)+$"), "(no matches)")
        self.assertIn("STD-role-list:1:", self.retriever.grep_pages("nothing here|cafe associate"))

    def test_read_page_accepts_bracketed_names_and_rejects_unknown(self):
        self.assertIn("Club C only", self.retriever.read_page("[STD-venue-access]"))
        self.assertIn("unknown page", self.retriever.read_page("SYN-ffffff"))


class CitationTests(unittest.TestCase):
    def test_invented_ids_are_dropped_and_duplicates_collapsed(self):
        retriever = retrieval.Retriever(PAGES)
        answer = "Yes [SYN-aaaaaa], per [STD-venue-access] and [SYN-ffffff]; again [SYN-aaaaaa]."
        self.assertEqual(retrieval.cited_pages(answer, retriever), ["SYN-aaaaaa", "STD-venue-access"])


class DeclineTests(unittest.TestCase):
    def test_decline_needs_the_prefix_and_colon(self):
        self.assertEqual(retrieval.decline_reason("**CANNOT ANSWER:** no record"), "no record")
        self.assertEqual(retrieval.decline_reason("Seen [STD-role-list].\nCANNOT ANSWER: nope"), "nope")
        self.assertIsNone(retrieval.decline_reason("Cannot answer the club part, but the role is X [STD-role-list]."))


class AnswerRuleTests(unittest.TestCase):
    # The wording was measured: a broader "any missing fact is an answer" broke q03's
    # decline for every agentic technique. Changing it means re-running measure_retrieval.py.
    def test_policy_gaps_decline_before_the_missing_fact_rule(self):
        policy = retrieval.SYSTEM.index("the standard does not address it")
        missing_fact = retrieval.SYSTEM.index("a specific ticket you found")
        self.assertLess(policy, missing_fact)
        self.assertIn("even if the question names\na ticket", retrieval.SYSTEM)

    def test_next_steps_must_come_from_a_record(self):
        self.assertIn("only if a record states it", retrieval.SYSTEM)


class RetryTests(unittest.TestCase):
    """The answer call owns one classified retry; litellm's own wrapper stays off."""

    def errors(self):
        from litellm import AuthenticationError, ServiceUnavailableError
        return (ServiceUnavailableError("down", llm_provider="x", model="m"),
                AuthenticationError("bad key", llm_provider="x", model="m"))

    def test_transient_error_is_retried_once_without_litellm_retries(self):
        unavailable, _ = self.errors()
        calls = []

        def completion(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise unavailable
            return reply("Answer [STD-role-list]")

        with patch.object(retrieval.litellm, "completion", side_effect=completion), \
                patch.object(retrieval.time, "sleep"):
            result = retrieval.run_agent("q", "agentic_bm25", retrieval.Retriever(PAGES))
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call["num_retries"] == 0 for call in calls))
        self.assertEqual(result["stopped"], "answer")

    def test_client_error_is_not_retried(self):
        _, bad_key = self.errors()
        with patch.object(retrieval.litellm, "completion", side_effect=bad_key) as completion, \
                patch.object(retrieval.time, "sleep"):
            with self.assertRaises(type(bad_key)):
                retrieval.run_agent("q", "agentic_bm25", retrieval.Retriever(PAGES))
        self.assertEqual(completion.call_count, 1)

    def test_second_transient_error_is_raised(self):
        unavailable, _ = self.errors()
        with patch.object(retrieval.litellm, "completion", side_effect=unavailable) as completion, \
                patch.object(retrieval.time, "sleep"):
            with self.assertRaises(type(unavailable)):
                retrieval.run_agent("q", "agentic_bm25", retrieval.Retriever(PAGES))
        self.assertEqual(completion.call_count, 2)


class LoopTests(unittest.TestCase):
    def test_model_cannot_call_methods_outside_its_technique(self):
        retriever = retrieval.Retriever(PAGES)
        replies = iter([reply(tool_calls=[tool_call("_embed", '{"texts": ["x"]}')]), reply("No answer.")])
        with patch.object(retrieval.litellm, "completion", side_effect=lambda **_: next(replies)), \
                patch.object(retrieval.Retriever, "_embed") as embed:
            result = retrieval.run_agent("q", "agentic_bm25", retriever)
        embed.assert_not_called()
        self.assertEqual(result["trace"][0]["tool"], "_embed")
        self.assertEqual(result["stopped"], "answer")

    def test_non_object_arguments_become_a_tool_error(self):
        retriever = retrieval.Retriever(PAGES)
        replies = iter([reply(tool_calls=[tool_call("search_chunks", "[1]")]), reply("No answer.")])
        with patch.object(retrieval.litellm, "completion", side_effect=lambda **_: next(replies)):
            result = retrieval.run_agent("q", "agentic_bm25", retriever)
        self.assertEqual(result["trace"][0]["args"], {})
        self.assertLess(result["trace"][0]["chars"], 60)  # the short "(tool error: ...)" string

    def test_embedding_outage_inside_a_tool_is_raised_not_swallowed(self):
        retriever = retrieval.Retriever(PAGES)
        call = reply(tool_calls=[tool_call("search_hybrid", '{"query": "Lifeguard"}')])
        with patch.object(retrieval.litellm, "completion", return_value=call), \
                patch.object(retrieval.Retriever, "_embed", side_effect=APITimeoutError(request=None)):
            with self.assertRaises(APITimeoutError):
                retrieval.run_agent("q", "agentic_hybrid", retriever)

    def test_loop_stops_at_the_turn_budget(self):
        retriever = retrieval.Retriever(PAGES)
        looping = reply(tool_calls=[tool_call("search_chunks", '{"query": "Lifeguard"}')])
        with patch.object(retrieval.litellm, "completion", return_value=looping):
            result = retrieval.run_agent("q", "agentic_bm25", retriever, max_turns=3)
        self.assertEqual((result["stopped"], result["calls"], result["answer"]), ("max_turns", 3, ""))


if __name__ == "__main__":
    unittest.main()
