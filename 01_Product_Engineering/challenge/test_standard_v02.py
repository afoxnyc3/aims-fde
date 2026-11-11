"""Role-matrix standard (v0.2 format) policy tests. Synthetic standard only; mocked extraction."""
import os
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

import onboarding
import standard_v02
from schema import Request, Status, solve

SYNTHETIC = """
version: "0.2-test"
business_unit: {id: "unit-test", name: "Test Unit"}
venues: {in_club: ["Club A", "Club B"]}
out_of_scope_business_units: ["Golf Club"]
out_of_scope_venue_prefixes: ["Annex"]
aliases: {"Desk Associate Level 1": "Desk Associate", "Level 2 Coach": "Coach"}
non_bundle_systems: ["Prospr", "Zoho", "Monday.com"]
roles:
  - {title: "Desk Associate", staff_login: true,  company_mailbox: false, account_role: "Desk Associate"}
  - {title: "Coach",          staff_login: true,  company_mailbox: true,  account_role: "Coach"}
  - {title: "Personal Trainer", staff_login: true, company_mailbox: true, account_role: "Trainer"}
  - {title: "Cafe Associate", staff_login: false, company_mailbox: false, account_role: null}
  - {title: "Desk Manager",   staff_login: true,  company_mailbox: true,  account_role: null}
  - {title: "Pool Captain",   staff_login: null,  company_mailbox: null,  account_role: null}
  - {title: "Guard",          staff_login: true,  company_mailbox: false, account_role: "Desk Associate", account_role_scope: business_unit}
  - {title: "Therapist",      staff_login: true,  company_mailbox: false, account_role: "Trainer", staff_group: "Therapist"}
  - {title: "Instructor",     staff_login: true,  company_mailbox: false, account_role: "Senior Instructor", caveat: "Senior Instructor carries staff admin; owner-approved SOP."}
"""


def facts(**kw):
    v = dict(request_kind="onboarding", person_name="Example Hire", job_title="Desk Associate Level 1",
             employee_email="hire@example.invalid", start_date="2026-11-01", venue_names=["Club A"],
             business_unit=None, login_required=True, person_id=None, personal_trainer_level=None,
             ambiguous_identity=False, additional_access_request=None)
    v.update(kw)
    return onboarding.ExtractedTicket(**v)


class StandardV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.path = Path(cls.dir.name) / "std.yaml"
        cls.path.write_text(SYNTHETIC)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def run_with(self, extracted):
        req = Request(ticket_ref="T-1", ticket_text="Synthetic", comments=[])
        with patch.dict(os.environ, {"ONBOARDING_STANDARD": str(self.path)}), \
             patch("onboarding.extract_ticket", return_value=extracted):
            return solve(req)

    def test_recommended_with_login_and_role(self):
        r = self.run_with(facts())
        self.assertEqual(r.status, Status.RECOMMENDED)
        self.assertTrue(r.answer.staff_login)
        self.assertEqual(r.answer.assignments[0].role.name, "Desk Associate")
        self.assertEqual([v.name for v in r.answer.venues], ["Club A"])

    def test_business_unit_scoped_role_is_granted_once_at_the_unit(self):
        r = self.run_with(facts(job_title="Guard", venue_names=["Club A", "Club B"]))
        self.assertEqual(r.status, Status.RECOMMENDED)
        self.assertEqual(len(r.answer.assignments), 1)
        a = r.answer.assignments[0]
        self.assertEqual((a.role.name, a.scope_type, a.scope.name), ("Desk Associate", "business_unit", "Test Unit"))
        self.assertEqual([v.name for v in r.answer.venues], ["Club A", "Club B"])

    def test_title_staff_group_is_granted_at_each_club(self):
        r = self.run_with(facts(job_title="Therapist", venue_names=["Club A", "Club B"]))
        self.assertEqual(r.status, Status.RECOMMENDED)
        self.assertEqual([(g.staff_group.name, g.scope_type, g.scope.name) for g in r.answer.staff_groups],
                         [("Therapist", "venue", "Club A"), ("Therapist", "venue", "Club B")])
        self.assertEqual(self.run_with(facts()).answer.staff_groups, [])  # no group on the title, none granted

    def test_owner_caveat_travels_with_the_recommendation(self):
        r = self.run_with(facts(job_title="Instructor"))
        self.assertEqual(r.status, Status.RECOMMENDED)
        self.assertEqual(r.answer.assignments[0].role.name, "Senior Instructor")
        self.assertIn("Senior Instructor carries staff admin; owner-approved SOP.", r.caveats)
        self.assertNotIn("Senior Instructor carries staff admin; owner-approved SOP.", self.run_with(facts()).caveats)

    def test_a_named_system_outside_the_bundle_is_an_exception(self):
        for text in ("Guard needs prospr to sub at fitness", "Please give access to all Zoho accounts", "Add to Monday.com"):
            with self.subTest(text=text):
                r = self.run_text(text, facts())
                self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, "exception"))
                self.assertTrue(any("systems beyond the role bundle" in d for d in r.exception_difference))
        for text in ("Synthetic", "Prosprity is not a system", "zohobar"):  # whole names only
            with self.subTest(text=text):
                self.assertEqual(self.run_text(text, facts()).status, Status.RECOMMENDED)

    def test_owner_caveat_travels_with_an_exception_review_that_proposes_the_role(self):
        r = self.run_text("Needs a laptop", facts(job_title="Instructor"))
        self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, "exception"))
        self.assertIsNotNone(r.standard_proposal)
        self.assertIn("Senior Instructor carries staff admin; owner-approved SOP.", r.jira_comment)
        r = self.run_text("Needs a laptop", facts(job_title="Instructor", person_name=None))  # no proposal, no grant to warn about
        self.assertIsNone(r.standard_proposal)
        self.assertNotIn("carries staff admin", r.jira_comment)

    def test_venue_scoped_role_is_granted_per_club(self):
        r = self.run_with(facts(venue_names=["Club A", "Club B"]))
        self.assertEqual([(a.scope_type, a.scope.name) for a in r.answer.assignments], [("venue", "Club A"), ("venue", "Club B")])

    def test_no_login_role_gets_member_record_only(self):
        r = self.run_with(facts(job_title="Cafe Associate"))
        self.assertEqual(r.status, Status.RECOMMENDED)
        self.assertFalse(r.answer.staff_login)
        self.assertEqual((r.answer.assignments, r.answer.login_email, r.answer.staff_groups), ([], None, []))

    def test_personal_email_only_asked_when_no_company_mailbox(self):
        r = self.run_with(facts(employee_email=None))
        self.assertEqual((r.status, r.missing_fields), (Status.NEEDS_INFORMATION, ["personal_email"]))
        r = self.run_with(facts(job_title="Level 2 Coach", employee_email=None, personal_trainer_level=2))
        self.assertEqual(r.status, Status.RECOMMENDED)

    def test_missing_title_and_venue(self):
        r = self.run_with(facts(job_title=None, venue_names=[]))
        self.assertEqual(r.missing_fields, ["job_title", "venue"])

    def test_review_reasons(self):
        cases = {"exception": facts(additional_access_request="same access as a colleague"),
                 "ambiguous_mapping": facts(job_title="Brand Ambassador"),
                 "role_unmapped": facts(job_title="Desk Manager"),
                 "standard_gap": facts(job_title="Pool Captain"),
                 "out_of_scope_business_unit": facts(venue_names=["Golf Club"]),
                 "duplicate": facts(marked_duplicate=True)}
        for reason, f in cases.items():
            with self.subTest(reason=reason):
                r = self.run_with(f)
                self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, reason))

    def test_exception_outranks_unmapped_title(self):
        r = self.run_with(facts(job_title="Brand Ambassador", rehire_transfer_or_promotion=True))
        self.assertEqual(r.review_reason, "exception")

    def test_rehire_with_missing_fields_goes_to_review_not_an_ask(self):
        # A re-hire needs a person whatever the requester answers, so asking first is a wasted round trip.
        # The missing fields travel in the handoff instead, for the reviewer to collect.
        for f in (facts(person_name=None, rehire_transfer_or_promotion=True), facts(person_name=None)):
            text = "Re-hire: YES" if not f.rehire_transfer_or_promotion else "Synthetic"
            with self.subTest(flagged_by="extraction" if f.rehire_transfer_or_promotion else "intake text"):
                r = self.run_text(text, f)
                self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, "exception"))
                self.assertEqual(r.missing_fields, [])  # missing_fields means "ask the requester": needs_information only
                # The gap travels as data, not only as prose in the comment.
                self.assertEqual((r.review_missing_fields, r.contradictory_fields), (["person_name"], []))
                self.assertIn("person_name", r.jira_comment)
                self.assertIsNone(r.standard_proposal)  # nothing is proposed while a fact is missing
                self.assertNotIn("Assign the standard tier", r.jira_comment)  # there is no tier to assign
        r = self.run_with(facts(person_name=None))  # not a re-hire: still an ask
        self.assertEqual((r.status, r.missing_fields), (Status.NEEDS_INFORMATION, ["person_name"]))

    def test_any_exception_with_missing_fields_goes_to_review_not_an_ask(self):
        # Owner, 2026-11-10: hardware, mirror, non-standard start and extra access need a person anyway.
        for text, f in (("Needs a laptop", facts(person_name=None)),
                        ("Same access as her manager", facts(person_name=None)),
                        ("Contractor start", facts(person_name=None)),
                        ("Synthetic", facts(person_name=None, additional_access_request="extra system"))):
            with self.subTest(text=text):
                r = self.run_text(text, f)
                self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, "exception"))
                self.assertEqual(r.review_missing_fields, ["person_name"])
                self.assertIsNone(r.standard_proposal)
        r = self.run_text("Was promoted last year", facts(person_name=None))  # the broad regex alone still asks
        self.assertEqual((r.status, r.missing_fields), (Status.NEEDS_INFORMATION, ["person_name"]))

    def test_rehire_handoff_names_the_gap_and_the_extra_access(self):
        # Code review finding: a second exception branch once wrote "re-hire" alone and dropped the extra access.
        r = self.run_text("Re-hire: YES", facts(person_name=None, additional_access_request="also let her sell memberships"))
        self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, "exception"))
        self.assertIn("person_name", r.jira_comment)
        self.assertEqual(r.review_missing_fields, ["person_name"])
        for comment in (r.jira_comment, " ".join(r.exception_difference)):
            self.assertIn("also let her sell memberships", comment)
            self.assertIn("re-hire", comment)  # the reason the ask was skipped is named too
        # exception_difference is the access beyond the standard, one item per reason: no gaps, no instructions.
        self.assertEqual(r.exception_difference, ["also let her sell memberships", "re-hire"])

    def test_rehire_with_gaps_landing_in_an_earlier_review_still_hands_them_over(self):
        # It skipped the ask on the promise that the gaps travel with the review, whichever review it lands in.
        for reason, extra in (("out_of_scope_business_unit", dict(venue_names=["Golf Club"])),
                              ("ambiguous_identity", dict(ambiguous_identity=True)),
                              ("duplicate", dict(marked_duplicate=True))):
            with self.subTest(reason=reason):
                r = self.run_with(facts(person_name=None, rehire_transfer_or_promotion=True, **extra))
                self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, reason))
                self.assertIn("Missing from the intake: person_name.", r.jira_comment)
        r = self.run_with(facts(marked_duplicate=True))  # nothing missing: the comment is unchanged
        self.assertEqual(r.jira_comment, "The ticket marks itself a duplicate; confirm before acting.")

    def test_flagged_rehire_is_named_even_when_the_broad_transfer_regex_fires(self):
        r = self.run_text("Previously promoted to lead.", facts(person_name=None, rehire_transfer_or_promotion=True))
        self.assertEqual(r.exception_difference, ["transfer or promotion", "re-hire, transfer, promotion or title change"])

    def test_flagged_transfer_and_promotion_with_a_gap_go_to_review_not_an_ask(self):
        # Owner decision 2026-11-07: transfers and promotions follow the re-hire rule. Straight to review, gaps listed,
        # no ask. "Flagged" means extraction set the flag; the broad regex alone does not skip an ask (test below).
        for kind, text in (("transfer", "Transferring from Club B to Club A."), ("promotion", "Promoted to Desk Associate.")):
            with self.subTest(kind=kind):
                r = self.run_text(text, facts(job_title=None, rehire_transfer_or_promotion=True))
                self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, "exception"))
                self.assertEqual(r.missing_fields, [])
                self.assertEqual(r.review_missing_fields, ["job_title"])
                self.assertIn("job_title", r.jira_comment)
                self.assertIsNone(r.standard_proposal)

    def test_a_stray_promotion_does_not_suppress_an_ask(self):
        r = self.run_text("Will help run the January membership promotion", facts(venue_names=[]))
        self.assertEqual((r.status, r.missing_fields), (Status.NEEDS_INFORMATION, ["venue"]))

    def test_rehire_handoff_carries_no_proposal_while_anything_is_missing(self):
        # A tier built on incomplete facts reads as "the standard tier": no trainer group, or a bad login.
        for name, f in (("trainer level", facts(job_title="Personal Trainer", personal_trainer_level=None)),
                        ("unusable email", facts(employee_email="med.2290")),
                        ("contradictory venue", facts(intake_contradiction="venue"))):
            with self.subTest(gap=name):
                r = self.run_with(f.model_copy(update={"rehire_transfer_or_promotion": True}))
                self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, "exception"))
                self.assertIsNone(r.standard_proposal)
                self.assertNotIn("Assign the standard tier", r.jira_comment)
                self.assertIn("No standard tier can be proposed yet", r.jira_comment)
        r = self.run_with(facts(rehire_transfer_or_promotion=True))  # nothing missing: the baseline is still there
        self.assertIsNotNone(r.standard_proposal)
        self.assertIn("Assign the standard tier", r.jira_comment)
        self.assertEqual((r.review_missing_fields, r.contradictory_fields), ([], []))

    def test_exception_without_a_baseline_never_says_assign_the_tier(self):
        # An unmapped title has no standard tier either, gaps or not.
        r = self.run_with(facts(job_title="Brand Ambassador", rehire_transfer_or_promotion=True))
        self.assertIsNone(r.standard_proposal)
        self.assertNotIn("Assign the standard tier", r.jira_comment)

    def test_flagged_rehire_is_named_beside_another_trigger(self):
        r = self.run_text("Also needs a laptop.", facts(person_name=None, rehire_transfer_or_promotion=True))
        self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, "exception"))
        self.assertIn("hardware", r.jira_comment)
        self.assertIn("re-hire, transfer, promotion or title change", r.jira_comment)  # why the ask was skipped

    def test_rehire_handoff_names_a_mirror_the_intake_also_asks_for(self):
        # Extraction missed the mirror; the regex backstop caught it second, after "re-hire". Both are named.
        r = self.run_text("Re-hire: YES. Same access as Priya Okafor.", facts(person_name=None))
        self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, "exception"))
        self.assertEqual(r.exception_difference, ["re-hire", "mirror or copy another user's access"])
        self.assertIn("re-hire; mirror or copy another user's access", r.jira_comment)

    def test_rehire_handoff_calls_a_conflict_contradictory_not_missing(self):
        r = self.run_with(facts(rehire_transfer_or_promotion=True, intake_contradiction="employee_email"))
        self.assertIn("Contradictory in the intake: personal_email.", r.jira_comment)
        self.assertNotIn("Missing from the intake", r.jira_comment)
        self.assertEqual((r.review_missing_fields, r.contradictory_fields), ([], ["personal_email"]))
        r = self.run_with(facts(rehire_transfer_or_promotion=True, person_name=None, intake_contradiction="venue"))
        self.assertIn("Missing from the intake: person_name. Contradictory in the intake: venue.", r.jira_comment)
        self.assertEqual((r.review_missing_fields, r.contradictory_fields), (["person_name"], ["venue"]))

    def test_review_gap_fields_are_rejected_except_on_an_exception_review(self):
        from pydantic import ValidationError
        from schema import Response
        req = Request(ticket_ref="T-6", ticket_text="Synthetic", comments=[])
        others = {
            "recommended": self.run_with(facts()),
            "needs_information": self.run_with(facts(person_name=None)),
            "human_review (not exception)": self.run_with(facts(ambiguous_identity=True)),
            "ignored": self.run_with(facts(request_kind="other")),
            "failed": onboarding.outcome(req, Status.FAILED, "The onboarding standard is unavailable."),
            "exception with a standard proposal": self.run_with(facts(rehire_transfer_or_promotion=True)),
        }
        self.assertEqual([r.status.value for r in others.values()],
                         ["recommended", "needs_information", "human_review", "ignored", "failed", "human_review"])
        allowed = self.run_with(facts(person_name=None, rehire_transfer_or_promotion=True))
        self.assertEqual((allowed.review_reason, allowed.standard_proposal), ("exception", None))
        for field in ("review_missing_fields", "contradictory_fields"):
            for label, r in others.items():
                with self.subTest(field=field, status=label):
                    with self.assertRaises(ValidationError):
                        Response.model_validate({**r.model_dump(), field: ["venue"]})
            with self.subTest(field=field, status="exception without a proposal"):
                Response.model_validate({**allowed.model_dump(), field: ["venue"]})  # accepted
        with self.assertRaises(ValidationError):  # one field is missing or contradictory, not both
            Response.model_validate({**allowed.model_dump(), "review_missing_fields": ["venue"],
                                     "contradictory_fields": ["venue"]})

    def test_rehire_handoff_lists_every_gap(self):
        # The earlier review reasons keep precedence: test_rehire_with_gaps_landing_in_an_earlier_review_...
        r = self.run_with(facts(person_name=None, job_title=None, rehire_transfer_or_promotion=True))
        self.assertIn("person_name, job_title", r.jira_comment)
        self.assertEqual(r.review_missing_fields, ["person_name", "job_title"])

    def test_review_findings_round1(self):
        r = self.run_with(facts(ambiguous_identity=True))
        self.assertEqual(r.review_reason, "ambiguous_identity")
        r = self.run_with(facts(business_unit="Golf Club"))            # excluded unit at a known club
        self.assertEqual(r.review_reason, "out_of_scope_business_unit")
        r = self.run_with(facts(start_date=None))
        self.assertEqual(r.status, Status.RECOMMENDED)
        self.assertIsNone(r.answer.start_date)                          # never fabricated
        r = self.run_with(facts(job_title="Level 2 Coach"))             # company-mailbox role
        self.assertTrue(r.answer.company_mailbox)
        self.assertIsNone(r.answer.login_email)                         # no placeholder text as a login

    def test_review_findings_round2(self):
        req = Request(ticket_ref="T-4", ticket_text="Synthetic", comments=[])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.yaml"
            p.write_text(SYNTHETIC)
            with patch.dict(os.environ, {"ONBOARDING_STANDARD": str(p)}), \
                 patch("onboarding.extract_ticket", return_value=facts(job_title="Cafe Associate")):
                self.assertEqual(solve(req).status, Status.RECOMMENDED)
                p.write_text(SYNTHETIC.replace('"Cafe Associate", staff_login: false', '"Cafe Associate", staff_login: null')
                             + "\n")                                    # edited: becomes a matrix gap
                self.assertEqual(solve(req).review_reason, "standard_gap")  # not served from a stale cache
                p.write_text(SYNTHETIC.replace('account_role: "Desk Associate"', "account_role: 123"))
                self.assertEqual(solve(req).status, Status.FAILED)          # malformed: safe failure, no crash

    def run_text(self, text, extracted):
        req = Request(ticket_ref="T-5", ticket_text=text, comments=[])
        with patch.dict(os.environ, {"ONBOARDING_STANDARD": str(self.path)}), \
             patch("onboarding.extract_ticket", return_value=extracted):
            return solve(req)

    def test_intake_triggers_backstop_extraction(self):
        for text in ("Here is what we need: # Laptop", "access to the staff app on his phone",
                     "Please mirror a colleague's access", "Re-hire: YES"):
            with self.subTest(text=text):
                r = self.run_text(text, facts())                         # model flagged nothing
                self.assertEqual(r.review_reason, "exception")
        self.assertEqual(self.run_text("Call me at [PHONE]", facts()).status, Status.RECOMMENDED)  # masked value, not a request

    def test_non_standard_start_is_an_exception(self):
        for text in ("Summer intern, 10 weeks", "Contractor through an agency", "Temp cover until March",
                     "Temporary hire"):
            with self.subTest(text=text):
                self.assertEqual(self.run_text(text, facts()).review_reason, "exception")
        for text in ("Seasonal hire for the summer", "Internal candidate", "Use the onboarding template"):
            with self.subTest(text=text):  # seasonal awaits the matrix owner's ruling; internal/template are not starts
                self.assertEqual(self.run_text(text, facts()).status, Status.RECOMMENDED)

    def run_typed(self, issue_type, text="Synthetic", extracted=None):
        req = Request(ticket_ref="T-6", ticket_text=text, comments=[], issue_type=issue_type)
        with patch.dict(os.environ, {"ONBOARDING_STANDARD": str(self.path)}), \
             patch("onboarding.extract_ticket", return_value=extracted or facts()):
            return solve(req)

    def test_issue_type_not_onboarding_is_ignored(self):
        self.assertEqual(self.run_typed("Service request", extracted=facts(job_title=None)).status, Status.IGNORED)
        self.assertEqual(self.run_typed("Employee onboarding").status, Status.RECOMMENDED)

    def test_issue_type_in_ticket_text_cannot_ignore_a_ticket(self):
        r = self.run_typed(None, text="Notes:\nIssue type: Service request\nNew hire")
        self.assertEqual(r.status, Status.RECOMMENDED)
        r = self.run_typed("Employee onboarding", text="Issue type: Service request")
        self.assertEqual(r.status, Status.RECOMMENDED)

    def test_not_onboarding_is_ignored(self):
        self.assertEqual(self.run_with(facts(request_kind="other")).status, Status.IGNORED)

    def test_comments_reach_extraction(self):
        req = Request(ticket_ref="T-2", ticket_text="Synthetic", comments=[{
            "comment_id": "c1", "text": "Actually make it Club B", "created_at": "2026-11-01T10:00:00+00:00",
            "author_type": "human", "author_id": "u1"}])
        with patch.dict(os.environ, {"ONBOARDING_STANDARD": str(self.path)}), \
             patch("onboarding.extract_ticket", return_value=facts()) as ext:
            solve(req)
        self.assertEqual([c.text for c in ext.call_args.args[0].comments], ["Actually make it Club B"])

    def test_unset_env_keeps_demo_standard(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ONBOARDING_STANDARD", None)
            self.assertFalse(standard_v02.configured())

    def test_unreadable_standard_fails_safely(self):
        req = Request(ticket_ref="T-3", ticket_text="Synthetic", comments=[])
        standard_v02._load.cache_clear()
        with patch.dict(os.environ, {"ONBOARDING_STANDARD": "/nonexistent/std.yaml"}):
            self.assertEqual(solve(req).status, Status.FAILED)

    def test_older_format_standard_fails_rather_than_reading_as_blank(self):
        req = Request(ticket_ref="T-7", ticket_text="Synthetic", comments=[])
        for label, text in (("role keys", SYNTHETIC.replace("staff_login:", "other_login:")),
                            ("no unit", SYNTHETIC.replace('business_unit: {id: "unit-test", name: "Test Unit"}\n', ""))):
            with self.subTest(label), tempfile.TemporaryDirectory() as d:
                p = Path(d) / "s.yaml"
                p.write_text(text)
                with patch.dict(os.environ, {"ONBOARDING_STANDARD": str(p)}), \
                     patch("onboarding.extract_ticket", return_value=facts()):
                    self.assertEqual(solve(req).status, Status.FAILED)

    def test_out_of_scope_venue_prefix_comes_from_the_standard(self):
        self.assertEqual(self.run_with(facts(venue_names=["Annex Pool"])).review_reason, "out_of_scope_business_unit")
        self.assertEqual(self.run_with(facts(venue_names=["Annexe"])).review_reason, "ambiguous_mapping")

    def test_trainer_group_uses_the_standards_unit(self):
        r = self.run_with(facts(job_title="Personal Trainer", personal_trainer_level=2))
        self.assertEqual(r.answer.staff_groups[0].scope.name, "Test Unit")

    def test_repeated_venue_is_one_venue(self):
        r = self.run_with(facts(venue_names=["Club A", "club a"]))
        self.assertEqual(r.status, Status.RECOMMENDED)
        self.assertEqual([v.name for v in r.answer.venues], ["Club A"])
        self.assertEqual(len(r.answer.assignments), 1)

    def test_missing_or_unusable_facts_are_asked_for(self):
        cases = {"person_name": facts(person_name=None),
                 "personal_trainer_level": facts(job_title="Personal Trainer"),
                 "personal_email": facts(employee_email="not an email")}
        for field, f in cases.items():
            with self.subTest(field):
                r = self.run_with(f)
                self.assertEqual((r.status, r.missing_fields), (Status.NEEDS_INFORMATION, [field]))

    def test_exception_review_carries_the_named_baseline(self):
        r = self.run_with(facts(additional_access_request="extra access"))
        self.assertEqual(r.standard_proposal.person_name, "Example Hire")

    def test_login_disagreement_is_a_caveat(self):
        r = self.run_with(facts(login_required=False))
        self.assertEqual(r.status, Status.RECOMMENDED)
        self.assertTrue(any("not required" in c and "a login" in c for c in r.caveats))
        r = self.run_with(facts(job_title="Cafe Associate", login_required=True))
        self.assertTrue(any("required" in c and "no login" in c for c in r.caveats))
        self.assertEqual(self.run_with(facts()).caveats, ["Existing-account status was not checked."])

    def test_email_contradiction_only_asks_when_the_address_is_used(self):
        r = self.run_with(facts(job_title="Coach", intake_contradiction="employee_email"))
        self.assertEqual(r.status, Status.RECOMMENDED)
        r = self.run_with(facts(intake_contradiction="employee_email"))
        self.assertEqual(r.missing_fields, ["personal_email"])
        r = self.run_with(facts(employee_email=None, intake_contradiction="employee_email"))
        self.assertEqual(r.missing_fields, ["personal_email"])

    def test_venue_contradiction_is_asked_once(self):
        r = self.run_with(facts(venue_names=[], intake_contradiction="venue"))
        self.assertEqual(r.missing_fields, ["venue"])

    # Owner's name policy, 2026-11-07: a legal surname is required; no surname goes back to the requesting manager.
    def test_has_surname_shapes(self):
        cases = {
            "Sam": False,                          # single token
            "sam.smith@example.invalid": False,    # email handle
            "ssmith": False,                       # bare handle
            "sam.smith": False,                    # dotted handle, no space
            "S.": False,                           # initial only
            "S. J.": False,                        # initials only
            "Sam S.": False,                       # a surname initial is not a surname
            "  Sam,  ": False,                     # whitespace and punctuation around a single name
            None: False,
            "": False,
            "Sam Smith": True,
            "  Sam Smith.  ": True,                # surrounding whitespace and punctuation
            "Ana García-López": True,              # hyphenated, non-ASCII
            "Van der Berg": True,                  # multi-part surname
            "Riley O'Neill": True,                 # apostrophe
            "Smith, Sam": True,                    # surname first
            "Mr Smith": False,                     # a title is not a given name
            "Sam Jr.": False,                      # a suffix is not a surname
            "Dr. Sam Smith III": True,
            "Sam Smith <sam.smith@example.invalid>": True,  # an email beside a full name is ignored
            "Sam sam.smith@example.invalid": False,
            unicodedata.normalize("NFD", "José García"): True,  # decomposed accents, as some exports send them
            "अनिल कुमार": True,                    # Devanagari vowel signs are combining marks
            "王小明": False,                        # no spaces between names: asked, a reviewer decides
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertIs(standard_v02.has_surname(name), expected)

    def test_first_name_only_is_asked_for_the_surname(self):
        r = self.run_with(facts(person_name="Sam"))
        self.assertEqual((r.status, r.missing_fields), (Status.NEEDS_INFORMATION, ["person_name"]))
        self.assertIsNone(r.answer)
        self.assertIn("without a legal surname", r.jira_comment)
        r = self.run_with(facts(person_name=None))
        self.assertNotIn("surname", r.jira_comment)  # no name at all: the plain ask

    def test_a_full_name_is_unchanged(self):
        r = self.run_with(facts(person_name="Ana García-López"))
        self.assertEqual(r.status, Status.RECOMMENDED)
        self.assertEqual(r.answer.person_name, "Ana García-López")
        self.assertEqual(r.missing_fields, [])

    def test_flagged_rehire_with_a_first_name_only_goes_to_review_with_the_gap(self):
        r = self.run_text("Re-hire: YES", facts(person_name="Sam"))
        self.assertEqual((r.status, r.review_reason), (Status.HUMAN_REVIEW, "exception"))
        self.assertEqual(r.missing_fields, [])
        self.assertEqual(r.review_missing_fields, ["person_name"])
        self.assertIsNone(r.standard_proposal)
        self.assertIn("without a legal surname", r.jira_comment)  # the reviewer is told a name was given

    def test_dockerfile_copies_the_module_onboarding_imports(self):
        self.assertIn("standard_v02.py", (Path(__file__).parent / "Dockerfile").read_text())


# v0.4 shape: pool clubs, the pool rule, and role groups (synthetic names only).
SYNTHETIC_V04 = """
version: "0.4-test"
business_unit: {id: "unit-test", name: "Test Unit"}
venues: {in_club: ["Club A", "Club B", "Club D"]}
pool_clubs: ["Club A", "Club D"]
pool_roles_outside_pool_club: needs_information
roles:
  - {title: "Lifeguard",      group: Aquatics,            staff_login: true, company_mailbox: false, account_role: "Lifeguard"}
  - {title: "Aquatics Lead",  group: Aquatics,            staff_login: true, company_mailbox: false, account_role: "Aquatics Lead"}
  - {title: "Desk Associate", group: Hospitality,         staff_login: true, company_mailbox: false, account_role: "Desk Associate"}
  - {title: "Coach",          group: Group Fitness,       staff_login: true, company_mailbox: true,  account_role: "Coach"}
  - {title: "Trainer",        group: Personal Training,   staff_login: true, company_mailbox: true,  account_role: "Trainer"}
  - {title: "Club Manager",   group: Managers,            staff_login: true, company_mailbox: true,  account_role: "Club Manager"}
  - {title: "Odd Job",        group: Unlisted Group,      staff_login: true, company_mailbox: true,  account_role: "Odd Job"}
"""


def v04_facts(**kw):
    return facts(**{"job_title": "Lifeguard", **kw})


class StandardV04Tests(unittest.TestCase):
    """The pool rule, the exception approver and version selection (owner decisions, 2026-11-07)."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.path = Path(cls.dir.name) / "std.yaml"
        cls.path.write_text(SYNTHETIC_V04)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def run_with(self, extracted, text="Synthetic"):
        req = Request(ticket_ref="T-40", ticket_text=text, comments=[])
        with patch.dict(os.environ, {"ONBOARDING_STANDARD": str(self.path)}), \
             patch("onboarding.extract_ticket", return_value=extracted):
            return solve(req)

    def test_pool_role_at_a_pool_club_is_unchanged(self):
        for title in ("Lifeguard", "Aquatics Lead"):
            for club in ("Club A", "Club D"):
                with self.subTest(title=title, club=club):
                    r = self.run_with(v04_facts(job_title=title, venue_names=[club]))
                    self.assertEqual(r.status, Status.RECOMMENDED)
                    self.assertEqual(r.answer.assignments[0].role.name, title)

    def test_pool_role_at_a_non_pool_club_asks_for_venue_confirmation(self):
        for title in ("Lifeguard", "Aquatics Lead"):
            for venues in (["Club B"], ["Club A", "Club B"]):  # one non-pool club is enough to ask
                with self.subTest(title=title, venues=venues):
                    r = self.run_with(v04_facts(job_title=title, venue_names=venues))
                    self.assertEqual(r.status, Status.NEEDS_INFORMATION)
                    self.assertEqual(r.missing_fields, ["venue_confirmation"])
        self.assertEqual(self.run_with(v04_facts(job_title="Desk Associate", venue_names=["Club B"])).status,
                         Status.RECOMMENDED)  # the rule is for pool roles only

    def test_confirmed_pool_role_at_a_non_pool_club_goes_to_the_business_unit_owner(self):
        # Service desk, 2026-11-09: once the requester confirms the club, a person reviews; no second ask.
        r = self.run_with(v04_facts(venue_names=["Club B"], venue_confirmed=True))
        self.assertEqual(r.status, Status.HUMAN_REVIEW)
        self.assertEqual(r.review_reason, "exception")
        self.assertEqual(r.missing_fields, [])
        self.assertTrue(any("pool" in d for d in r.exception_difference))
        self.assertEqual(r.approval_owner_role, "VP of Operations (Fitness)")  # Lifeguard: Aquatics
        self.assertIn("Approver: VP of Operations (Fitness).", r.jira_comment)
        self.assertIsNotNone(r.standard_proposal)

    def test_venue_confirmation_changes_nothing_at_a_pool_club(self):
        r = self.run_with(v04_facts(venue_names=["Club A"], venue_confirmed=True))
        self.assertEqual(r.status, Status.RECOMMENDED)

    def test_pool_rule_does_not_replace_a_missing_venue(self):
        r = self.run_with(v04_facts(venue_names=[]))
        self.assertEqual(r.missing_fields, ["venue"])

    def test_flagged_rehire_at_a_non_pool_club_goes_to_review_with_venue_confirmation(self):
        r = self.run_with(v04_facts(venue_names=["Club B"], rehire_transfer_or_promotion=True))
        self.assertEqual(r.status, Status.HUMAN_REVIEW)
        self.assertEqual(r.review_reason, "exception")
        self.assertEqual(r.missing_fields, [])
        self.assertEqual(r.review_missing_fields, ["venue_confirmation"])
        self.assertIsNone(r.standard_proposal)
        self.assertIn("venue_confirmation", r.jira_comment)

    def test_rehire_transfer_or_promotion_approver_is_the_service_desk_manager(self):
        for label, kw, text in (("flag", {"rehire_transfer_or_promotion": True}, "Synthetic"),
                                ("Re-hire: YES", {}, "Re-hire: YES")):
            with self.subTest(label):
                r = self.run_with(v04_facts(job_title="Coach", **kw), text=text)
                self.assertEqual(r.review_reason, "exception")
                self.assertEqual(r.approval_owner_role, "Service Desk Manager")
                self.assertIn("Approver: Service Desk Manager.", r.jira_comment)
        r = self.run_with(v04_facts(venue_names=["Club B"], rehire_transfer_or_promotion=True))  # with a gap
        self.assertEqual(r.approval_owner_role, "Service Desk Manager")

    def test_every_group_has_the_owner_the_project_owner_assigned(self):
        # The project owner's assignment (2026-11-10, with the business development manager's review), one line per
        # group: a changed owner must change here too. Managers depends on the club, so it is checked below.
        expected = {
            "Accounting": "VP of Finance (Fitness)",
            "Aquatics": "VP of Operations (Fitness)",
            "Cafe": "Food & Beverage Director",
            "Childcare": "VP Hospitality or Business Development Manager (Fitness)",
            "Group Fitness": "Senior Group Fitness Manager or Group Fitness Director",
            "Hospitality": "VP Hospitality or Business Development Manager (Fitness)",
            "Housekeeping": "VP of Operations (Fitness)",
            "Human Resources": "HR / People Ops Director",
            "Maintenance": "VP of Operations (Fitness)",
            "Marketing": "VP Marketing",
            "Massage": "VP Hospitality or Business Development Manager (Fitness)",
            "Member Services": "VP Hospitality or Business Development Manager (Fitness)",
            "Membership Sales": "VP of Membership Sales (Fitness)",
            "Personal Training": "Director of Personal Training",
            "Rockwall": "General Manager (Club A)",
            "Special Events": "Events Director",
            "Technology": "Senior Director IT or CTO",
        }
        self.assertEqual(set(expected) | {"Managers"}, set(standard_v02.BUSINESS_UNIT_OWNERS))
        for group, owner in expected.items():
            with self.subTest(group=group):
                self.assertEqual(standard_v02._approver({"group": group}, False, [], None), owner)
        self.assertEqual(standard_v02._approver({"group": "Technology"}, True, [], None), "Service Desk Manager")

    def test_other_exceptions_go_to_the_roles_business_unit_owner(self):
        for title, owner in (("Lifeguard", "VP of Operations (Fitness)"),
                             ("Desk Associate", "VP Hospitality or Business Development Manager (Fitness)"),
                             ("Coach", "Senior Group Fitness Manager or Group Fitness Director"),  # either approves
                             ("Trainer", "Director of Personal Training"),
                             ("Odd Job", "Service Desk Manager"),       # group with no owner yet: the desk
                             ("Not In Matrix", "Service Desk Manager")):  # no role at all
            with self.subTest(title=title):
                r = self.run_with(v04_facts(job_title=title), text="Please mirror a colleague's access")
                self.assertEqual(r.review_reason, "exception")
                self.assertEqual(r.approval_owner_role, owner)
                self.assertIn(f"Approver: {owner}.", r.jira_comment)

    def test_a_club_managers_exception_goes_to_that_clubs_general_manager(self):
        for club in ("Club B", "Club D"):
            with self.subTest(club=club):
                r = self.run_with(v04_facts(job_title="Club Manager", venue_names=[club]),
                                  text="Please mirror a colleague's access")
                self.assertEqual(r.review_reason, "exception")
                self.assertEqual(r.approval_owner_role, f"General Manager ({club})")
                self.assertIn(f"Approver: General Manager ({club}).", r.jira_comment)
        role = {"group": "Managers"}
        venues = {"club b": {"name": "Club B"}, "club d": {"name": "Club D"}}
        for names in ([], ["club b", "club d"], ["club b", "somewhere else"], ["somewhere else"]):  # the desk routes
            with self.subTest(names=names):
                self.assertEqual(standard_v02._approver(role, False, names, {"venues": venues}), "Service Desk Manager")
        self.assertEqual(standard_v02._approver(role, False, ["club b"], None), "Service Desk Manager")
        # A club manager's re-hire, transfer or promotion still goes to the desk, not the club's GM.
        self.assertEqual(standard_v02._approver(role, True, ["club b"], {"venues": venues}), "Service Desk Manager")
        r = self.run_with(v04_facts(job_title="Club Manager", venue_names=["Club B"], rehire_transfer_or_promotion=True))
        self.assertEqual(r.approval_owner_role, "Service Desk Manager")

    def test_a_transfer_named_only_in_the_intake_goes_to_the_service_desk_manager(self):
        r = self.run_with(v04_facts(job_title="Coach"), text="Transferring from Club B")  # extraction did not flag it
        self.assertEqual(r.review_reason, "exception")
        self.assertEqual(r.approval_owner_role, "Service Desk Manager")

    def test_venue_confirmation_is_explained_to_the_requester(self):
        r = self.run_with(v04_facts(venue_names=["Club B"]))
        self.assertIn("a pool role at a club with no pool", r.jira_comment)

    def test_pool_roles_come_from_the_standard_when_listed(self):
        p = Path(self.dir.name) / "roles.yaml"
        p.write_text(SYNTHETIC_V04.replace("pool_roles_outside_pool_club:", 'pool_roles: ["desk associate"]\npool_roles_outside_pool_club:'))
        req = Request(ticket_ref="T-42", ticket_text="Synthetic", comments=[])
        with patch.dict(os.environ, {"ONBOARDING_STANDARD": str(p)}):
            for title, status in (("Desk Associate", Status.NEEDS_INFORMATION), ("Lifeguard", Status.RECOMMENDED)):
                with self.subTest(title=title), patch("onboarding.extract_ticket",
                                                       return_value=v04_facts(job_title=title, venue_names=["Club B"])):
                    self.assertEqual(solve(req).status, status)

    def test_malformed_pool_and_group_settings_fail_safely(self):
        req = Request(ticket_ref="T-43", ticket_text="Synthetic", comments=[])
        for label, text in (("misspelt rule", SYNTHETIC_V04.replace("outside_pool_club: needs_information", "outside_pool_club: needs_info")),
                            ("unknown club", SYNTHETIC_V04.replace('pool_clubs: ["Club A", "Club D"]', 'pool_clubs: ["Club Z"]')),
                            ("list group", SYNTHETIC_V04.replace("group: Aquatics,", "group: [Aquatics],", 1)),
                            ("unquoted version", SYNTHETIC_V04.replace('version: "0.4-test"', "version: 0.10"))):
            with self.subTest(label), tempfile.TemporaryDirectory() as d:
                p = Path(d) / "s.yaml"
                p.write_text(text)
                with patch.dict(os.environ, {"ONBOARDING_STANDARD": str(p)}), \
                     patch("onboarding.extract_ticket", return_value=v04_facts()):
                    self.assertEqual(solve(req).status, Status.FAILED)

    def test_an_empty_pool_clubs_key_means_no_pool_rule(self):
        p = Path(self.dir.name) / "nopool.yaml"
        p.write_text(SYNTHETIC_V04.replace('pool_clubs: ["Club A", "Club D"]', "pool_clubs:"))
        req = Request(ticket_ref="T-44", ticket_text="Synthetic", comments=[])
        with patch.dict(os.environ, {"ONBOARDING_STANDARD": str(p)}), \
             patch("onboarding.extract_ticket", return_value=v04_facts(venue_names=["Club B"])):
            self.assertEqual(solve(req).status, Status.RECOMMENDED)

    def test_only_exception_reviews_name_an_approver(self):
        r = self.run_with(v04_facts(job_title="Not In Matrix"))
        self.assertEqual(r.review_reason, "ambiguous_mapping")
        self.assertIsNone(r.approval_owner_role)


class StandardVersionTests(unittest.TestCase):
    """v0.5 is the default from 2026-11-10; TC4 stays pinned to v0.3 (owner decision, 2026-11-07)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        for v in ("0.3", "0.4", "0.5"):
            text = SYNTHETIC_V04.replace('version: "0.4-test"', f'version: "{v}"')
            (Path(self.dir.name) / standard_v02.FILENAME.format(version=v)).write_text(text)
        standard_v02._load.cache_clear()

    def env(self, **kw):
        base = {k: "" for k in (standard_v02.ENV, standard_v02.DIR_ENV, standard_v02.VERSION_ENV)}
        return patch.dict(os.environ, {**base, standard_v02.DIR_ENV: self.dir.name, **kw})

    def test_defaults_and_pins(self):
        self.assertEqual(standard_v02.DEFAULT_VERSION, "0.5")
        self.assertEqual(standard_v02.TC4_VERSION, "0.3")

    def test_directory_selects_the_default_version(self):
        with self.env():
            self.assertTrue(standard_v02.configured())
            self.assertEqual(standard_v02.load_standard()["version"], "0.5")

    def test_version_can_be_selected(self):
        with self.env(ONBOARDING_STANDARD_VERSION="0.3"):
            self.assertEqual(standard_v02.load_standard()["version"], "0.3")
        with self.env():
            self.assertEqual(standard_v02.load_standard(standard_v02.TC4_VERSION)["version"], "0.3")

    def test_an_explicit_path_still_wins(self):
        p = Path(self.dir.name) / "other.yaml"
        p.write_text(SYNTHETIC_V04)
        with self.env(ONBOARDING_STANDARD=str(p)):
            self.assertEqual(standard_v02.load_standard()["version"], "0.4-test")

    def test_a_file_whose_version_disagrees_fails_safely(self):
        (Path(self.dir.name) / standard_v02.FILENAME.format(version=standard_v02.DEFAULT_VERSION)).write_text(SYNTHETIC_V04)  # says 0.4-test
        with self.env(), patch("onboarding.extract_ticket", return_value=v04_facts()):
            r = solve(Request(ticket_ref="T-41", ticket_text="Synthetic", comments=[]))
        self.assertEqual(r.status, Status.FAILED)

    def test_tc4_runner_pin_matches_the_module(self):
        run_py = (Path(__file__).resolve().parents[2] / "use_case/evals/run.py").read_text()
        self.assertIn(f'TC4_STANDARD_VERSION = "{standard_v02.TC4_VERSION}"', run_py)

    def test_a_version_set_beside_an_explicit_path_is_checked(self):
        p = Path(self.dir.name) / standard_v02.FILENAME.format(version="0.4")
        with self.env(ONBOARDING_STANDARD=str(p), ONBOARDING_STANDARD_VERSION="0.3"):
            with self.assertRaisesRegex(ValueError, "asked for standard v0.3"):
                standard_v02.load_standard()

    def test_a_version_without_the_directory_is_a_clear_error(self):
        with self.env(ONBOARDING_STANDARD_DIR="", ONBOARDING_STANDARD="/some/file.yaml"):
            with self.assertRaisesRegex(ValueError, "ONBOARDING_STANDARD_DIR"):
                standard_v02.load_standard(standard_v02.TC4_VERSION)

    def test_unknown_version_is_refused(self):
        with self.env(ONBOARDING_STANDARD_VERSION="../../etc/x"):
            with self.assertRaises(ValueError):
                standard_v02.standard_path()


if __name__ == "__main__":
    unittest.main()
