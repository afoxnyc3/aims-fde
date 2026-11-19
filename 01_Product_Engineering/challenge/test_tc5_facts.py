"""Offline tests for the several-lookups scorer: hand-written answers, no model, no server.

Runs under the challenge's own test command: python -m unittest test_tc5_facts
"""

import unittest
from pathlib import Path

import tc5_facts
from tc5_facts import UNSTATED, score_several_lookups

HERE = Path(__file__).parent

RIGHT_PROSE = """Here is what the standard says for each hire.

**1. Hospitality Associate Level 1**
- Role: use Front Desk Associate [STD-role-list]. "Hospitality Associate Level 1" is a legacy title.
- Company mailbox: the standard does not say.

**2. Lifeguard**
- Role: use Lifeguard [STD-role-list].
- Company mailbox: not stated in the standard.

**3. Personal Trainer Level 2**
- Role: use Personal Trainer [STD-role-list]. The level is a title variant.
- Company mailbox: the standard does not mention a mailbox.
"""

RIGHT_TABLE = """| Hire | Role to use | Company mailbox? |
|---|---|---|
| Hospitality Associate Level 1 | Front Desk Associate | Not stated |
| Lifeguard | Lifeguard | Not stated |
| Personal Trainer Level 2 | Personal Trainer | Not stated |
"""

RIGHT_GLOBAL_NOTE = """- Hospitality Associate Level 1: use Front Desk Associate.
- Lifeguard: use Lifeguard.
- Personal Trainer Level 2: use Personal Trainer.

The standard does not cover company mailboxes for any of these roles.
"""

WRONG = """- Hospitality Associate Level 1: use Hospitality Associate. Company mailbox: yes.
- Lifeguard: use Aquatics Lead. Company mailbox: yes.
- Personal Trainer Level 2: use Group Fitness Instructor. Company mailbox: yes.
"""

PARTIAL = """**Hospitality Associate Level 1**
- Role: use Front Desk Associate.
- Company mailbox: yes, they get a company mailbox.

**Lifeguard**
- Role: use Lifeguard.
- Company mailbox: no, a Lifeguard does not get a company mailbox.

**Personal Trainer Level 2**
- Role: use Personal Trainer Level 2.
- Company mailbox: the standard does not say.
"""

REJECTED = """**Hospitality Associate Level 1**
- Do not use Front Desk Associate. Keep the title as it is on the ticket.
- Company mailbox: the standard does not say.

**Lifeguard**
- Role: use Lifeguard.
- Company mailbox: the standard does not say.

**Personal Trainer Level 2**
- Role: use Personal Trainer.
- Company mailbox: the standard does not say.
"""


class ExpectedValuesTest(unittest.TestCase):
    """The expected values are the synthetic standard's, read from the file the corpus is built from."""

    def setUp(self):
        self.standard = (HERE / "standard_v0_1.md").read_text()

    def test_roles_are_rows_of_the_standard_role_list(self):
        rows = [line.split("|")[1].strip() for line in self.standard.splitlines() if line.startswith("| ")]
        for hire in tc5_facts.HIRES.values():
            self.assertIn(hire["role"], rows)

    def test_the_hospitality_title_is_a_variant_of_front_desk_associate(self):
        row = next(line for line in self.standard.splitlines() if line.startswith("| Front Desk Associate"))
        self.assertIn("Hospitality Associate Level 1", row)
        self.assertEqual(tc5_facts.HIRES["hospitality"]["role"], "Front Desk Associate")

    def test_the_standard_never_mentions_a_mailbox(self):
        self.assertNotIn("mailbox", self.standard.lower())
        for hire in tc5_facts.HIRES.values():
            self.assertEqual(hire["mailbox"], UNSTATED)


class ScorerTest(unittest.TestCase):
    def test_right_answer_in_prose_scores_six(self):
        out = score_several_lookups(RIGHT_PROSE)
        self.assertEqual(out["facts_right"], 6)
        self.assertEqual(set(out["facts"]), {"hospitality_role", "hospitality_mailbox", "lifeguard_role",
                                             "lifeguard_mailbox", "trainer_role", "trainer_mailbox"})
        self.assertTrue(all(out["facts"].values()))

    def test_right_answer_in_a_table_scores_six(self):
        self.assertEqual(score_several_lookups(RIGHT_TABLE)["facts_right"], 6)

    def test_one_note_about_all_three_counts_for_each_hire(self):
        self.assertEqual(score_several_lookups(RIGHT_GLOBAL_NOTE)["facts_right"], 6)

    def test_wrong_answer_scores_zero(self):
        out = score_several_lookups(WRONG)
        self.assertEqual(out["facts_right"], 0)
        self.assertFalse(any(out["facts"].values()))

    def test_partial_answer_is_scored_per_fact(self):
        out = score_several_lookups(PARTIAL)
        self.assertEqual(out["facts"], {
            "hospitality_role": True, "hospitality_mailbox": False,   # a yes the standard does not give
            "lifeguard_role": True, "lifeguard_mailbox": False,       # a no the standard does not give
            "trainer_role": False, "trainer_mailbox": True,           # the level is not part of the role
        })
        self.assertEqual(out["facts_right"], 3)

    def test_naming_the_role_in_order_to_reject_it_is_wrong(self):
        out = score_several_lookups(REJECTED)
        self.assertFalse(out["facts"]["hospitality_role"])
        self.assertEqual(out["facts_right"], 5)

    def test_rejecting_the_old_title_does_not_reject_the_role(self):
        answer = RIGHT_PROSE.replace("use Front Desk Associate [STD-role-list].",
                                     "use Front Desk Associate, not Hospitality Associate.")
        self.assertTrue(score_several_lookups(answer)["facts"]["hospitality_role"])

    def test_a_value_stated_for_another_hire_does_not_count(self):
        answer = """- Hospitality Associate Level 1: the ticket title stands.
- Lifeguard: use Lifeguard.
- Personal Trainer Level 2: use Personal Trainer. Company mailbox: the standard does not say.
"""
        facts = score_several_lookups(answer)["facts"]
        self.assertFalse(facts["hospitality_role"])
        self.assertFalse(facts["hospitality_mailbox"])  # said for the trainer only
        self.assertFalse(facts["lifeguard_mailbox"])
        self.assertTrue(facts["trainer_mailbox"])

    def test_the_hire_title_alone_is_not_a_role_answer(self):
        answer = "The Lifeguard and the Personal Trainer Level 2 start Monday. The standard does not say " \
                 "anything about mailboxes for any of these roles."
        facts = score_several_lookups(answer)["facts"]
        self.assertFalse(facts["lifeguard_role"])
        self.assertFalse(facts["trainer_role"])

    def test_a_yes_about_the_login_is_not_a_yes_about_the_mailbox(self):
        answer = RIGHT_PROSE.replace("- Company mailbox: the standard does not say.",
                                     "- Staff login: yes, at all clubs.\n- Company mailbox: the standard does not say.")
        self.assertTrue(score_several_lookups(answer)["facts"]["hospitality_mailbox"])

    def test_mixed_mailbox_statements_for_one_hire_are_wrong(self):
        answer = RIGHT_PROSE.replace("- Company mailbox: not stated in the standard.",
                                     "- Company mailbox: not stated in the standard.\n- They get a company mailbox.")
        self.assertFalse(score_several_lookups(answer)["facts"]["lifeguard_mailbox"])

    def test_remarks_that_are_not_about_getting_a_mailbox_do_not_count(self):
        # Phrasings like these came back in the 2026-11-18 runs and are right by hand.
        answer = RIGHT_GLOBAL_NOTE + (
            "It only covers the staff login, not a company mailbox or email account for any role. "
            "Don't read the login column as a mailbox decision. "
            "Tickets have an employee email field. It isn't a mailbox entitlement. "
            "So the standard doesn't give a mailbox, and it doesn't rule one out. "
            "They don't give a mailbox to any role, and they don't withhold one.")
        self.assertEqual(score_several_lookups(answer)["facts_right"], 6)

    def test_a_negation_that_is_not_about_using_the_role_is_not_a_rejection(self):
        answer = RIGHT_GLOBAL_NOTE + "You didn't name the club, so I can't give the Lifeguard answer for your club."
        self.assertTrue(score_several_lookups(answer)["facts"]["lifeguard_role"])
        for rejection in ("Do not use Lifeguard for this hire.", "The role is not Lifeguard.",
                          "Use Aquatics Lead rather than Lifeguard."):
            self.assertFalse(score_several_lookups(RIGHT_GLOBAL_NOTE + rejection)["facts"]["lifeguard_role"], rejection)

    def test_a_flat_no_is_still_wrong_after_a_general_note(self):
        answer = RIGHT_GLOBAL_NOTE + "The Lifeguard does not get a company mailbox."
        facts = score_several_lookups(answer)["facts"]
        self.assertFalse(facts["lifeguard_mailbox"])
        self.assertTrue(facts["trainer_mailbox"])

    # Cases from the review of the first committed scorer: each of these scored too high.
    def test_swapped_roles_score_no_role_facts(self):
        answer = """- Hospitality Associate Level 1: use Lifeguard.
- Lifeguard: use Personal Trainer.
- Personal Trainer Level 2: use Front Desk Associate.
The standard does not cover company mailboxes for any of these roles.
"""
        facts = score_several_lookups(answer)["facts"]
        self.assertEqual([facts["hospitality_role"], facts["lifeguard_role"], facts["trainer_role"]], [False] * 3)
        table = """| Hire | Role to use | Company mailbox? |
|---|---|---|
| Hospitality Associate Level 1 | Lifeguard | Not stated |
| Lifeguard | Personal Trainer | Not stated |
| Personal Trainer Level 2 | Front Desk Associate | Not stated |
"""
        self.assertEqual(score_several_lookups(table)["facts_right"], 3)

    def test_the_right_role_named_later_for_another_purpose_does_not_count(self):
        answer = RIGHT_PROSE.replace("use Front Desk Associate [STD-role-list].", "use Hospitality Associate.") + \
            "\nStaff login:\n- Front Desk Associate gets a staff login at all clubs.\n"
        self.assertFalse(score_several_lookups(answer)["facts"]["hospitality_role"])

    def test_a_list_of_roles_with_no_mapping_is_not_an_answer(self):
        answer = ("The standard roles are Front Desk Associate, Lifeguard and Personal Trainer. "
                  "I can't tell which hire maps to which.")
        facts = score_several_lookups(answer)["facts"]
        self.assertEqual([facts["hospitality_role"], facts["lifeguard_role"], facts["trainer_role"]], [False] * 3)

    def test_repeating_the_question_scores_zero(self):
        self.assertEqual(score_several_lookups(
            "Three new hires start Monday at the same club: a Hospitality Associate Level 1, a Lifeguard and a "
            "Personal Trainer Level 2. For each one, which role do I use, and does the standard give them a "
            "company mailbox?")["facts_right"], 0)

    def test_more_ways_of_rejecting_the_role(self):
        for line in ("Front Desk Associate would be the wrong choice here; keep the title.",
                     "there is no match; Front Desk Associate does not apply.",
                     "use Front Desk Associate? No, that is incorrect, Front Desk Associate is not the role."):
            answer = RIGHT_PROSE.replace("use Front Desk Associate [STD-role-list].", line)
            self.assertFalse(score_several_lookups(answer)["facts"]["hospitality_role"], line)

    def test_a_hedge_next_to_a_yes_is_not_a_right_mailbox_answer(self):
        for note in ("The standard does not say, but yes, all three get a company mailbox.",
                     "It is unclear why you ask, since a mailbox is standard for all three.",
                     "The standard never mentions that a mailbox is denied to anyone, so all three get a mailbox.",
                     "The mailbox policy only covers full-time staff, so all three get a mailbox.",
                     "The standard does not say, but no, none of the three gets a mailbox."):
            answer = RIGHT_GLOBAL_NOTE.replace(
                "The standard does not cover company mailboxes for any of these roles.", note)
            out = score_several_lookups(answer)
            self.assertEqual(out["facts_right"], 3, note)

    def test_whether_they_get_one_is_not_a_yes(self):
        answer = RIGHT_GLOBAL_NOTE + ("I can't tell you whether any of these three gets a mailbox. "
                                      "The standard doesn't say that any of them gets a company mailbox. "
                                      "It has no mailbox or email entitlement for any role.")
        self.assertEqual(score_several_lookups(answer)["facts_right"], 6)

    # Cases from the second review round.
    def test_swapped_roles_under_headings_score_wrong(self):
        two_way = RIGHT_PROSE.replace("- Role: use Lifeguard [STD-role-list].", "- Role: use Personal Trainer.") \
                             .replace("- Role: use Personal Trainer [STD-role-list].", "- Role: use Lifeguard.")
        facts = score_several_lookups(two_way)["facts"]
        self.assertEqual([facts["hospitality_role"], facts["lifeguard_role"], facts["trainer_role"]],
                         [True, False, False])
        for heading in ("**{}**", "### {}", "{}"):
            three_way = "\n".join([
                heading.format("Hospitality Associate Level 1"), "- Role: use Lifeguard.",
                "- Company mailbox: the standard does not say.",
                heading.format("Lifeguard"), "Use Personal Trainer.", "- Company mailbox: the standard does not say.",
                heading.format("Personal Trainer Level 2"), "- Role: Front Desk Associate.",
                "- Company mailbox: the standard does not say."])
            self.assertEqual(score_several_lookups(three_way)["facts_right"], 3, heading)

    def test_a_mailbox_answer_stays_with_the_heading_after_a_swapped_role(self):
        answer = RIGHT_PROSE.replace("- Role: use Front Desk Associate [STD-role-list]. \"Hospitality Associate "
                                     "Level 1\" is a legacy title.\n- Company mailbox: the standard does not say.",
                                     "- Role: use Lifeguard.\n- Company mailbox: yes.")
        found = score_several_lookups(answer)["found"]
        self.assertEqual(found["hospitality_mailbox"], "yes")
        self.assertEqual(found["lifeguard_mailbox"], UNSTATED)

    def test_the_title_after_a_plain_label_is_not_the_role(self):
        for lifeguard in ("Hire: Lifeguard\nRole: Aquatics Lead", "- Title: Lifeguard. Use Aquatics Lead.",
                          "Hire 2: Lifeguard, no matching role.", "I could not find the role for the Lifeguard."):
            answer = RIGHT_GLOBAL_NOTE.replace("- Lifeguard: use Lifeguard.", lifeguard)
            self.assertFalse(score_several_lookups(answer)["facts"]["lifeguard_role"], lifeguard)

    def test_cannot_and_similar_wordings_reject_the_role(self):
        for line in ("You cannot use Front Desk Associate.", "This title cannot be mapped to Front Desk Associate.",
                     "It would be wrong to use Front Desk Associate.",
                     "use anything other than Front Desk Associate."):
            answer = RIGHT_PROSE.replace("use Front Desk Associate [STD-role-list].", line)
            self.assertFalse(score_several_lookups(answer)["facts"]["hospitality_role"], line)

    def test_one_sentence_naming_all_three_is_scored_clause_by_clause(self):
        note = " The standard does not cover company mailboxes for any of these roles."
        right = ("The Hospitality Associate Level 1 uses Front Desk Associate, the Lifeguard uses Lifeguard, "
                 "and the Personal Trainer Level 2 uses Personal Trainer.")
        swapped = ("The Hospitality Associate Level 1 should use Lifeguard, the Lifeguard should use Personal "
                   "Trainer, and the Personal Trainer Level 2 should use Front Desk Associate.")
        self.assertEqual(score_several_lookups(right + note)["facts_right"], 6)
        self.assertEqual(score_several_lookups(swapped + note)["facts_right"], 3)

    # Cases from the third review round.
    def test_no_match_for_the_lifeguard_is_not_the_lifeguard_role(self):
        for lifeguard in ("- Lifeguard: no exact match in the standard; use Aquatics Lead.",
                          "- Lifeguard: I could not find an exact match in the standard.",
                          "- Lifeguard: there is no direct match in the standard.",
                          "- Lifeguard: the title does not map directly to a role; use Aquatics Lead.",
                          "- Lifeguard: Role: Aquatics Lead (no exact match for the title).",
                          "- Lifeguard: I can't confirm whether Lifeguard is a standard role.",
                          "- Lifeguard: title: Lifeguard, role: Pool Attendant.",
                          "- Lifeguard: the title used is Lifeguard; the role is Pool Attendant.",
                          "- Lifeguard: use Lifeguard Supervisor."):
            answer = RIGHT_GLOBAL_NOTE.replace("- Lifeguard: use Lifeguard.", lifeguard)
            out = score_several_lookups(answer)
            self.assertFalse(out["facts"]["lifeguard_role"], lifeguard)
            self.assertEqual(out["facts_right"], 5, lifeguard)

    def test_longer_role_names_and_late_verdicts_are_not_the_role(self):
        for line in ("use Front Desk Associate Lead.", "the role Front Desk Associate should not be assigned.",
                     "some would use Front Desk Associate, but that is a mistake.",
                     "Front Desk Associate no longer exists; use the ticket title."):
            answer = RIGHT_PROSE.replace("use Front Desk Associate [STD-role-list].", line)
            self.assertFalse(score_several_lookups(answer)["facts"]["hospitality_role"], line)
        answer = RIGHT_GLOBAL_NOTE.replace("use Personal Trainer.", "use Personal Trainer Manager.")
        self.assertFalse(score_several_lookups(answer)["facts"]["trainer_role"])

    # Cases from the fourth review round.
    def test_a_role_named_and_then_said_to_be_absent_is_rejected(self):
        cases = {
            "- Lifeguard: use Lifeguard.": (
                "lifeguard_role",
                ["- Lifeguard: Lifeguard is not in the standard; use Pool Attendant.",
                 "- Lifeguard: Lifeguard isn't in the standard.",
                 "- Lifeguard: Lifeguard is not found in the standard.",
                 "- Lifeguard: Lifeguard was not found; use Pool Attendant.",
                 "- Lifeguard: Lifeguard does not appear in the role list; use Pool Attendant.",
                 "- Lifeguard: Lifeguard has no entry in the role list; use Pool Attendant.",
                 "- Lifeguard: Lifeguard (not found in the standard; closest is Pool Attendant).",
                 "- Lifeguard: role: Lifeguard (not in the standard, so use Pool Attendant).",
                 "- Lifeguard: use Lifeguard or Pool Attendant.",
                 "- Lifeguard: use Lifeguard if it exists, otherwise Pool Attendant.",
                 "- Lifeguard: use Lifeguard (unconfirmed, I could not find it in the standard)."]),
            "- Hospitality Associate Level 1: use Front Desk Associate.": (
                "hospitality_role",
                ["- Hospitality Associate: Front Desk Associate is not listed; use Concierge.",
                 "- Hospitality Associate: Front Desk Associate isn't in the standard; use Concierge."]),
            "- Personal Trainer Level 2: use Personal Trainer.": (
                "trainer_role",
                ["- Personal Trainer Level 2: Personal Trainer isn't in the standard; use Fitness Coach."]),
        }
        for original, (fact, lines) in cases.items():
            for line in lines:
                out = score_several_lookups(RIGHT_GLOBAL_NOTE.replace(original, line))
                self.assertFalse(out["facts"][fact], line)
                self.assertEqual(out["facts_right"], 5, line)

    def test_a_no_about_the_login_or_mailbox_does_not_reject_the_role(self):
        answer = RIGHT_GLOBAL_NOTE.replace(
            "- Lifeguard: use Lifeguard.",
            "- Lifeguard: use Lifeguard, which does not get a staff login at Club A.")
        self.assertEqual(score_several_lookups(answer)["facts_right"], 6)

    # Cases from the fifth review round: both of the first two scored 6 of 6.
    def test_a_prohibition_around_the_right_role_is_a_rejection(self):
        answer = RIGHT_GLOBAL_NOTE.replace("use Front Desk Associate.", "It is forbidden to use Front Desk Associate.")
        out = score_several_lookups(answer)
        self.assertFalse(out["facts"]["hospitality_role"])
        self.assertEqual(out["facts_right"], 5)

    def test_a_hedge_followed_by_a_grant_is_not_a_right_mailbox_answer(self):
        answer = RIGHT_GLOBAL_NOTE.replace("The standard does not cover company mailboxes for any of these roles.",
                                           "The standard does not say, but all three are issued a company mailbox.")
        out = score_several_lookups(answer)
        self.assertEqual([out["facts"][f"{key}_mailbox"] for key in tc5_facts.HIRES], [False] * 3)
        self.assertEqual(out["facts_right"], 3)

    def test_other_prohibitions_and_negations_around_the_right_role(self):
        for line in ("You are not allowed to use Front Desk Associate.",
                     "You are not permitted to assign Front Desk Associate.",
                     "Using Front Desk Associate is prohibited.",
                     "Front Desk Associate is forbidden for this hire.",
                     "Front Desk Associate must be avoided.",
                     "Under no circumstances use Front Desk Associate.",
                     "Nobody should use Front Desk Associate.",
                     "Stop using Front Desk Associate.",
                     "Refrain from using Front Desk Associate.",
                     "I advise against using Front Desk Associate.",
                     "It is a mistake to use Front Desk Associate.",
                     "It would be incorrect to assign Front Desk Associate.",
                     "You shouldn't ever use Front Desk Associate.",
                     "The standard bars you from using Front Desk Associate.",
                     "Role: Front Desk Associate is off limits.",
                     "Front Desk Associate may not be used.",
                     "use Front Desk Associate? That is banned."):
            for right in (RIGHT_GLOBAL_NOTE, RIGHT_PROSE):
                original = "use Front Desk Associate [STD-role-list]." if right is RIGHT_PROSE else "use Front Desk Associate."
                out = score_several_lookups(right.replace(original, line))
                self.assertFalse(out["facts"]["hospitality_role"], line)
                self.assertEqual(out["facts_right"], 5, line)

    def test_other_hedges_followed_by_a_grant(self):
        for note in ("The standard does not say, but all three are assigned a company mailbox.",
                     "The standard does not say, however each of the three is granted a mailbox.",
                     "The standard is silent, though a company mailbox is assigned to all three.",
                     "The standard does not say. All three are issued a company mailbox.",
                     "The standard does not say, but all three will be set up with a mailbox.",
                     "The standard does not mention mailboxes, so all three get one.",
                     "It is not stated in the standard, yet a mailbox is allocated to all three.",
                     "The standard does not say, but in practice all three end up with a company mailbox.",
                     "Not stated, but all three are issued a mailbox anyway."):
            answer = RIGHT_GLOBAL_NOTE.replace(
                "The standard does not cover company mailboxes for any of these roles.", note)
            self.assertEqual(score_several_lookups(answer)["facts_right"], 3, note)

    def test_a_hedge_followed_by_another_hedge_or_another_topic_is_still_right(self):
        for note in ("The standard does not say anything about a mailbox, but it does list a staff login for each role.",
                     "The standard does not mention a mailbox for any of these roles, but you can ask the owner whether one is needed.",
                     "The standard does not say whether any of these three is issued a company mailbox.",
                     "The standard does not say anything about a mailbox for any of these roles, so I can't tell you they get one.",
                     "The standard does not cover mailboxes, but that does not mean a mailbox is denied to any of these roles."):
            answer = RIGHT_GLOBAL_NOTE.replace(
                "The standard does not cover company mailboxes for any of these roles.", note)
            self.assertEqual(score_several_lookups(answer)["facts_right"], 6, note)

    def test_empty_answer_scores_zero(self):
        self.assertEqual(score_several_lookups("")["facts_right"], 0)

    def test_found_values_are_reported_for_the_reader(self):
        found = score_several_lookups(PARTIAL)["found"]
        self.assertEqual(found["hospitality_mailbox"], "yes")
        self.assertEqual(found["lifeguard_mailbox"], "no")
        self.assertEqual(found["trainer_mailbox"], UNSTATED)


if __name__ == "__main__":
    unittest.main()
