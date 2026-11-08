"""Pins the three multi-turn scenarios and their scorers. No model calls.

    uv run --project 01_Product_Engineering/challenge python -m unittest discover -s use_case/evals
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parents[1] / "01_Product_Engineering" / "challenge"))

import scenarios  # noqa: E402

SCENARIOS = {s["id"]: s for s in scenarios.load_scenarios()}


def response(status, **kw):
    return json.dumps({"ticket_ref": "x", "status": status, "answer": None, "missing_fields": [], "review_reason": None, **kw})


ASK = response("needs_information", missing_fields=["person_name"])


def proposal(name):
    return {"person_name": name, "assignments": [], "venues": [{"id": "v", "name": "Venue B"}]}


class Requests(unittest.TestCase):
    def test_three_synthetic_scenarios_each_with_two_turns(self):
        self.assertEqual(sorted(SCENARIOS), ["SYN-ASK-001", "SYN-ASK-002", "SYN-ASK-003"])
        for s in SCENARIOS.values():
            self.assertEqual(len(scenarios.requests(s)), 2, s["id"])

    def test_a_follow_up_turn_is_the_same_ticket_plus_the_new_comment(self):
        first, second = scenarios.requests(SCENARIOS["SYN-ASK-001"])
        self.assertEqual(first["comments"], [])
        self.assertEqual(second["ticket_text"], first["ticket_text"])
        self.assertIn("Quennell", second["comments"][-1]["text"])
        self.assertNotIn("Riley", first["ticket_text"])  # no first name either: the ask on turn 1 is needed

    def test_every_turn_is_a_valid_endpoint_request(self):
        from schema import Request

        for s in SCENARIOS.values():
            for req in scenarios.requests(s):
                Request.model_validate_json(json.dumps(req))


class Scorers(unittest.TestCase):
    def score(self, sid, *turns):
        return scenarios.SCORERS[sid](list(turns), SCENARIOS[sid])

    def test_surname_follow_up_passes_only_when_recommended_for_that_name(self):
        right = response("recommended", answer=proposal("Riley Quennell"))
        self.assertEqual(self.score("SYN-ASK-001", ASK, right), 1.0)
        self.assertEqual(self.score("SYN-ASK-001", ASK, ASK), 0.0)  # asked again: the follow-up was ignored
        self.assertEqual(self.score("SYN-ASK-001", ASK, response("recommended", answer=proposal("Riley"))), 0.0)
        self.assertEqual(self.score("SYN-ASK-001", right, right), 0.0)  # recommended before it knew the name

    def test_rehire_goes_to_review_on_turn_one_not_an_ask(self):
        handoff = response("human_review", review_reason="exception", jira_comment="Missing from the intake: person_name.")
        review = response("human_review", review_reason="exception", jira_comment="Re-hire.")
        self.assertEqual(self.score("SYN-ASK-002", handoff, review), 1.0)
        self.assertEqual(self.score("SYN-ASK-002", ASK, review), 0.0)  # asked first: the wasted round trip
        self.assertEqual(self.score("SYN-ASK-002", review, review), 0.0)  # review, but the gap is not in the handoff
        invented = response("human_review", review_reason="exception", jira_comment="Missing from the intake: person_name.",
                            standard_proposal=proposal("Invented Person"))
        self.assertEqual(self.score("SYN-ASK-002", invented, review), 0.0)  # a baseline before the name is known
        baseline_later = response("human_review", review_reason="exception", standard_proposal=proposal("Marcus Ellery-Dunn"))
        self.assertEqual(self.score("SYN-ASK-002", handoff, baseline_later), 1.0)  # allowed once the name arrives
        self.assertEqual(self.score("SYN-ASK-002", handoff, response("recommended", answer=proposal("Marcus Ellery-Dunn"))), 0.0)
        self.assertEqual(self.score("SYN-ASK-002", handoff, response("human_review", review_reason="ambiguous_mapping")), 0.0)
        self.assertEqual(self.score("SYN-ASK-002", handoff, response("human_review", review_reason="exception", answer=proposal("Marcus Ellery-Dunn"))), 0.0)

    def test_mirror_is_refused_not_copied(self):
        review = response("human_review", review_reason="exception", standard_proposal=proposal("Jo Varga"))
        self.assertEqual(self.score("SYN-ASK-003", ASK, review), 1.0)
        self.assertEqual(self.score("SYN-ASK-003", ASK, response("recommended", answer=proposal("Jo Varga"))), 0.0)
        copied = response("human_review", review_reason="exception", standard_proposal=proposal("Priya Okafor"))
        self.assertEqual(self.score("SYN-ASK-003", ASK, copied), 0.0)
        accented = dict(SCENARIOS["SYN-ASK-003"], mirrored="Zoë Okafor")
        copied = response("human_review", review_reason="exception", standard_proposal=proposal("Zoë Okafor"))
        self.assertEqual(scenarios.mirror_refused([ASK, copied], accented), 0.0)

    def test_an_echo_or_garbage_turn_scores_zero(self):
        for sid in SCENARIOS:
            self.assertEqual(self.score(sid, "not json", "{}"), 0.0, sid)

    def test_run_scenario_feeds_each_turn_and_scores(self):
        seen = []
        replies = iter([ASK, response("recommended", answer=proposal("Riley Quennell"))])

        def system(req):
            seen.append(json.loads(req))
            return next(replies)

        result = scenarios.run_scenario(system, SCENARIOS["SYN-ASK-001"])
        self.assertEqual(result["score"], 1.0)
        self.assertEqual([len(r["comments"]) for r in seen], [0, 1])

    def test_the_oracle_passes_all_three(self):
        for s in SCENARIOS.values():
            self.assertEqual(scenarios.run_scenario(scenarios.make_oracle(s), s)["score"], 1.0, s["id"])


class SavedScenarioRun(unittest.TestCase):
    """run_all goes through helpers.harness.save after every turn, so a failure keeps what came before it."""

    def test_an_error_on_turn_two_keeps_turn_one_on_disk_and_the_run_goes_on(self):
        from helpers import harness

        oracles = {sid: scenarios.make_oracle(s) for sid, s in SCENARIOS.items()}
        calls = []

        def system(req):
            sid = json.loads(req)["ticket_ref"]
            calls.append(sid)
            if sid == "SYN-ASK-001" and calls.count(sid) == 2:
                raise ConnectionError("endpoint went away")
            return oracles[sid](req)

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "scenarios.json"
            report = scenarios.run_all(system, path, list(SCENARIOS.values()))
            saved = harness.load(path)
        self.assertEqual(saved.n, 3)
        self.assertEqual(saved.errors, 1)
        first = saved.results[0]
        self.assertIn("endpoint went away", first.error)
        self.assertEqual(len(json.loads(first.actual)), 1)  # turn 1 survived the failure on turn 2
        self.assertEqual(first.scores["scenario_pass"], 0.0)
        self.assertEqual([r.scores["scenario_pass"] for r in saved.results[1:]], [1.0, 1.0])  # the run went on
        self.assertAlmostEqual(saved.means["scenario_pass"], 2 / 3)
        self.assertEqual(saved.meta["scenario_ids"], sorted(SCENARIOS))
        self.assertEqual(report.fingerprint, saved.fingerprint)

    def test_a_crash_mid_run_saves_a_mean_over_finished_scenarios_only(self):
        from helpers import harness

        s1, s2, s3 = (SCENARIOS[sid] for sid in sorted(SCENARIOS))
        oracle = scenarios.make_oracle(s1)

        def system(req):
            if json.loads(req)["ticket_ref"] == "SYN-ASK-002":
                raise KeyboardInterrupt  # not an Exception: the run stops here, as a killed process would
            return oracle(req)

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.json"
            with self.assertRaises(KeyboardInterrupt):
                scenarios.run_all(system, path, [s1, s2, s3])
            saved = harness.load(path)
        self.assertEqual((saved.n, saved.meta["finished"]), (3, 1))
        self.assertEqual(saved.means, {"scenario_pass": 1.0})  # not 1/3: unfinished scenarios are not failures

    def test_a_scenario_its_scorer_cannot_read_fails_before_any_call(self):
        doubled = dict(SCENARIOS["SYN-ASK-001"], turns=SCENARIOS["SYN-ASK-001"]["turns"] * 2)
        calls = []
        with self.assertRaisesRegex(scenarios.ScenarioError, "4 turns and 2 expected"):
            scenarios.run_scenario(lambda req: calls.append(req), doubled)
        self.assertEqual(calls, [])

    def test_a_scorer_failure_is_not_reported_as_the_endpoints(self):
        s = SCENARIOS["SYN-ASK-001"]
        with mock.patch.dict(scenarios.SCORERS, {"SYN-ASK-001": lambda turns, scenario: 1 / 0}), \
             tempfile.TemporaryDirectory() as d:
            report = scenarios.run_all(scenarios.make_oracle(s), Path(d) / "x.json", [s])
        self.assertIn("ScenarioError: SYN-ASK-001: the scorer failed after every turn was answered", report.results[0].error)
        self.assertEqual(len(json.loads(report.results[0].actual)), 2)

    def test_the_file_is_written_after_every_turn(self):
        s = SCENARIOS["SYN-ASK-001"]
        oracle, seen = scenarios.make_oracle(s), []
        with tempfile.TemporaryDirectory() as d, mock.patch("helpers.harness.save", side_effect=lambda r, p: seen.append(r.results[0].actual)):
            scenarios.run_all(oracle, Path(d) / "x.json", [s])
        self.assertEqual([len(json.loads(a)) for a in seen], [1, 2, 2])  # after turn 1, after turn 2, at the end


V02 = """
version: "0.2-test"
business_unit: {id: "unit-test", name: "Fitness"}
venues: {in_club: ["Venue A", "Venue B"]}
out_of_scope_business_units: []
out_of_scope_venue_prefixes: []
aliases: {"Hospitality Associate Level 1": "Hospitality Associate"}
roles:
  - {title: "Hospitality Associate", staff_login: true, company_mailbox: false, account_role: "Front Desk Associate"}
"""


class PolicyWithStubbedExtraction(unittest.TestCase):
    """The v0.2 decision code on each turn, with extraction replaced by the facts a correct read gives. No model."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.path = Path(cls.dir.name) / "std.yaml"
        cls.path.write_text(V02)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def system(self, facts_per_turn):
        import onboarding
        from schema import Request, solve

        facts = iter(facts_per_turn)

        def call(req_json):
            base = dict(request_kind="onboarding", person_name=None, job_title="Hospitality Associate Level 1",
                        employee_email="hire.personal@example.invalid", start_date="2026-11-16", venue_names=["Venue B"],
                        business_unit="Fitness", login_required=True, person_id=None, personal_trainer_level=None,
                        ambiguous_identity=False, additional_access_request=None)
            base.update(next(facts))
            with mock.patch.dict(os.environ, {"ONBOARDING_STANDARD": str(self.path)}), \
                 mock.patch("onboarding.extract_ticket", return_value=onboarding.ExtractedTicket(**base)):
                return solve(Request.model_validate_json(req_json)).model_dump_json()

        return call

    def test_surname_follow_up(self):
        system = self.system([{}, {"person_name": "Riley Quennell"}])
        self.assertEqual(scenarios.run_scenario(system, SCENARIOS["SYN-ASK-001"])["score"], 1.0)

    def test_rehire_reaches_review_even_if_extraction_misses_the_flag(self):
        # Re-hire: YES is in the intake text, so the regex backstop catches it without the model, and it now
        # does so on turn 1, before the missing name would have asked (test_standard_v02 pins the order).
        system = self.system([{}, {"person_name": "Marcus Ellery-Dunn"}])
        self.assertEqual(scenarios.run_scenario(system, SCENARIOS["SYN-ASK-002"])["score"], 1.0)

    def test_mirror_refused_when_extraction_flags_it(self):
        system = self.system([{}, {"person_name": "Jo Varga", "additional_access_request": "set up like a colleague"}])
        self.assertEqual(scenarios.run_scenario(system, SCENARIOS["SYN-ASK-003"])["score"], 1.0)

    def test_a_mirror_in_a_comment_rests_on_extraction_alone(self):
        # Known gap, pinned: intake_trigger scans ticket_text, not comments, and "set her up like" is not in its
        # pattern. If extraction misses the mirror, the policy recommends, and the scorer must catch that.
        # TC5 failure analysis: start here. A live 0 on SYN-ASK-003 is this gap until the trace says otherwise.
        system = self.system([{}, {"person_name": "Jo Varga"}])
        self.assertEqual(scenarios.run_scenario(system, SCENARIOS["SYN-ASK-003"])["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
