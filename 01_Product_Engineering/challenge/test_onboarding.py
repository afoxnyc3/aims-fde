"""Policy and transport checks. Mocked extraction is not a live model evaluation."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gradio import Error

import app
import onboarding
from schema import Request, Response, solve


def facts(**overrides):
    values = dict(
        request_kind="onboarding", person_name="Example Hire", job_title="Hospitality Associate",
        employee_email="example.personal@example.invalid", start_date="2026-11-01",
        venue_names=["Venue A"], business_unit="Fitness", login_required=True, person_id=None,
        personal_trainer_level=None, ambiguous_identity=False, additional_access_request=None,
    )
    values.update(overrides)
    return onboarding.ExtractedTicket(**values)


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.request = Request(ticket_ref="DEMO-TEST", ticket_text="Synthetic ticket", comments=[])

    def run_with(self, extracted):
        with patch("onboarding.extract_ticket", return_value=extracted):
            return solve(self.request)

    def test_five_golden_policy_paths(self):
        golden_path = Path(__file__).resolve().parents[2] / "use_case/evals/golden.jsonl"
        rows = [json.loads(line) for line in golden_path.read_text().splitlines() if line.strip()][:5]
        self.assertEqual(len(rows), 5)
        inputs = [
            facts(person_name="Example Hire A", job_title="Hospitality Associate Level 1",
                  employee_email="hire.a.personal@example.invalid", start_date="2026-10-16", venue_names=["Venue B"]),
            facts(person_name="Example Hire B", job_title="Personal Trainer", personal_trainer_level=None),
            facts(person_name="Example Hire C", job_title="Hospitality Manager/ AGM"),
            facts(person_name="Example Hire D", job_title="Hospitality Associate Level 1",
                  employee_email="hire.d.personal@example.invalid", start_date="2026-10-07",
                  person_id="person-demo-04", additional_access_request="the ability to sell memberships at the front desk"),
            facts(request_kind="other"),
        ]
        for golden, extracted in zip(rows, inputs):
            with self.subTest(ticket=golden["input"]["ticket_ref"]):
                with patch("onboarding.extract_ticket", return_value=extracted):
                    result = solve(Request.model_validate(golden["input"]))
                expected = Response.model_validate(golden["output"])
                self.assertEqual(result.status, expected.status)
                self.assertEqual(result.review_reason, expected.review_reason)
                self.assertEqual(result.missing_fields, expected.missing_fields)
                if expected.answer:
                    self.assertEqual(result.answer.assignments, expected.answer.assignments)
                    self.assertEqual(result.answer.login_email, expected.answer.login_email)
                    self.assertEqual(result.answer.start_date, expected.answer.start_date)
                if expected.standard_proposal:
                    self.assertEqual(result.standard_proposal.assignments, expected.standard_proposal.assignments)
                Response.model_validate_json(result.model_dump_json())

    def test_venue_scoped_multi_venue_assignment(self):
        result = self.run_with(facts(job_title="Personal Trainer", personal_trainer_level=2,
                                     venue_names=["Venue A", "Venue B"]))
        self.assertEqual(result.status.value, "recommended")
        self.assertEqual({a.scope.id for a in result.answer.assignments}, {"venue-demo-a", "venue-demo-b"})
        self.assertEqual(result.answer.permissions, [])
        self.assertEqual(result.answer.staff_groups[-1].staff_group.id, "group-demo-trainer-2")

    def test_unknown_business_unit_requires_review(self):
        extracted = facts(business_unit="Sports")
        result = self.run_with(extracted)
        self.assertEqual(result.status.value, "human_review")
        self.assertEqual(result.review_reason, "ambiguous_mapping")
        self.assertIsNone(result.answer)

    def test_missing_business_unit_requires_information(self):
        result = self.run_with(facts(business_unit=None))
        self.assertEqual(result.status.value, "needs_information")
        self.assertIn("business_unit", result.missing_fields)
        self.assertIsNone(result.answer)

    def test_business_unit_scopes_use_resolved_standard_id(self):
        standard = onboarding.load_standard()
        standard["business_units"].append({"id": "unit-demo-sports", "name": "Sports"})
        with patch("onboarding.load_standard", return_value=standard):
            for extracted in [facts(business_unit=" sports "),
                              facts(business_unit="Sports", job_title="Personal Trainer", personal_trainer_level=2)]:
                with self.subTest(role=extracted.job_title):
                    result = self.run_with(extracted)
                    self.assertEqual(result.status.value, "recommended")
                    scoped = result.answer.assignments + result.answer.staff_groups
                    units = [a.scope.id for a in scoped if a.scope_type == "business_unit"]
                    self.assertEqual(units, ["unit-demo-sports"])

    def test_unsupported_role_is_ignored_before_identity_review(self):
        result = self.run_with(facts(job_title="Unsupported Role", ambiguous_identity=True))
        self.assertEqual(result.status.value, "ignored")
        self.assertIsNone(result.jira_comment)
        self.assertIsNone(result.answer)

    def test_bad_provider_request_returns_failed(self):
        from litellm import BadRequestError
        error = BadRequestError("synthetic provider rejection", model="demo", llm_provider="openai")
        with patch("llm.stream_reply", side_effect=error) as stream:
            result = solve(self.request)
        self.assertEqual(stream.call_count, 1)
        self.assertEqual(result.status.value, "failed")
        self.assertIsNone(result.answer)
        self.assertNotIn("synthetic provider rejection", result.rationale)

    def test_extraction_disables_sdk_retries_and_sets_timeout(self):
        with patch("llm.stream_reply", return_value=iter([facts().model_dump_json()])) as stream:
            self.assertEqual(solve(self.request).status.value, "recommended")
        self.assertEqual(stream.call_args.kwargs["timeout"], 60)
        self.assertEqual(stream.call_args.kwargs["num_retries"], 0)

    def test_rate_limit_gets_one_retry(self):
        from litellm import RateLimitError
        error = RateLimitError("synthetic rate limit", model="demo", llm_provider="openai")
        with patch("llm.stream_reply", side_effect=[error, iter([facts().model_dump_json()])]) as stream:
            with patch("onboarding.time.sleep") as sleep:
                result = solve(self.request)
        self.assertEqual(result.status.value, "recommended")
        self.assertEqual(stream.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_persistent_rate_limit_returns_failed_after_one_retry(self):
        from litellm import RateLimitError
        error = RateLimitError("synthetic rate limit", model="demo", llm_provider="openai")
        with patch("llm.stream_reply", side_effect=error) as stream:
            with patch("onboarding.time.sleep"):
                result = solve(self.request)
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(stream.call_count, 2)
        self.assertIsNone(result.answer)

    def test_token_limit_does_not_change_timeout_or_retries(self):
        import llm
        chunk = SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content="ok"), finish_reason="stop")])
        with patch("llm.completion", return_value=iter([chunk])) as completion:
            list(llm.stream_reply("Synthetic ticket", max_tokens=100))
        self.assertEqual(completion.call_args.kwargs["max_tokens"], 100)
        self.assertNotIn("timeout", completion.call_args.kwargs)
        self.assertNotIn("num_retries", completion.call_args.kwargs)

    def test_explicit_timeout_and_retries_are_forwarded(self):
        import llm
        chunk = SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content="ok"), finish_reason="stop")])
        with patch("llm.completion", return_value=iter([chunk])) as completion:
            list(llm.stream_reply("Synthetic ticket", timeout=30, num_retries=1))
        self.assertEqual(completion.call_args.kwargs["timeout"], 30)
        self.assertEqual(completion.call_args.kwargs["num_retries"], 1)
        self.assertNotIn("max_tokens", completion.call_args.kwargs)

    def test_unknown_venue_requires_review(self):
        self.assertEqual(self.run_with(facts(venue_names=["Unknown Venue"])).review_reason, "ambiguous_mapping")

    def test_identity_conflict_requires_review(self):
        self.assertEqual(self.run_with(facts(ambiguous_identity=True)).review_reason, "ambiguous_identity")

    def test_only_final_cumulative_json_is_parsed(self):
        final = facts().model_dump_json()
        with patch("llm.stream_reply", return_value=iter([final[:12], final])):
            result = solve(self.request)
        self.assertEqual(result.status.value, "recommended")

    def test_model_cannot_supply_policy_ids(self):
        bad = facts().model_dump(mode="json")
        bad["role_id"] = "model-invented-role"
        with patch("llm.stream_reply", return_value=iter([json.dumps(bad)])):
            result = solve(self.request)
        self.assertEqual(result.status.value, "failed")
        self.assertIsNone(result.answer)

    def test_chat_content_filter_is_visible(self):
        chunk = SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content=None), finish_reason="content_filter")])
        with patch("llm.completion", return_value=iter([chunk])):
            with self.assertRaisesRegex(Error, "content filter"):
                list(app.chat("Synthetic prompt"))

    def test_onboarding_content_filter_returns_specific_failed(self):
        chunk = SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content=None), finish_reason="content_filter")])
        with patch("llm.completion", return_value=iter([chunk])) as completion:
            result = solve(self.request)
        self.assertEqual(result.status.value, "failed")
        self.assertIn("content filter", result.rationale)
        self.assertNotIn("valid ticket facts", result.rationale)
        self.assertIsNone(result.answer)
        self.assertEqual(completion.call_count, 1)

    def test_empty_extraction_stream_returns_no_text_failure(self):
        with patch("llm.stream_reply", return_value=iter([])):
            result = solve(self.request)
        self.assertEqual(result.status.value, "failed")
        self.assertIn("no text", result.rationale)
        self.assertNotIn("content filter", result.rationale)

    def test_empty_provider_stream_is_not_mislabeled_as_filtered(self):
        with patch("llm.completion", return_value=iter([])):
            result = solve(self.request)
        self.assertEqual(result.status.value, "failed")
        self.assertIn("no text", result.rationale)
        self.assertNotIn("content filter", result.rationale)

    def test_chat_empty_stream_is_visible(self):
        with patch("llm.completion", return_value=iter([])):
            with self.assertRaisesRegex(Error, "no text"):
                list(app.chat("Synthetic prompt"))

    def test_filtered_partial_json_is_never_a_recommendation(self):
        chunks = [
            SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(content=facts().model_dump_json()), finish_reason=None)]),
            SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(content=None), finish_reason="content_filter")]),
        ]
        with patch("llm.completion", return_value=iter(chunks)):
            result = solve(self.request)
        self.assertEqual(result.status.value, "failed")
        self.assertIn("content filter", result.rationale)
        self.assertIsNone(result.answer)

    def test_normal_stream_and_usage_chunk_keep_cumulative_text(self):
        import llm
        chunks = [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello"), finish_reason=None)]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=" world"), finish_reason=None)]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")]),
            SimpleNamespace(choices=[]),
        ]
        with patch("llm.completion", return_value=iter(chunks)):
            self.assertEqual(list(llm.stream_reply("Synthetic prompt")), ["Hello", "Hello world"])

    def test_malformed_extraction_returns_failed(self):
        with patch("llm.stream_reply", return_value=iter(["not json"])):
            self.assertEqual(solve(self.request).status.value, "failed")

    def test_unexpected_bug_propagates(self):
        with patch("onboarding.extract_ticket", side_effect=TypeError("synthetic bug")):
            with self.assertRaises(TypeError):
                solve(self.request)

    def test_endpoint_rejects_invalid_input_without_response(self):
        with self.assertRaises(Error):
            app.recommend_onboarding_access('{"ticket_text":"missing reference"}')

    def test_endpoint_serializes_valid_response(self):
        with patch("onboarding.extract_ticket", return_value=facts(request_kind="other")):
            result = Response.model_validate_json(app.recommend_onboarding_access(self.request.model_dump_json()))
        self.assertEqual(result.status.value, "ignored")
        self.assertIsNone(result.jira_comment)


if __name__ == "__main__":
    unittest.main()
