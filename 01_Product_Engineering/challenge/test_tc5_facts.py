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

    def test_empty_answer_scores_zero(self):
        self.assertEqual(score_several_lookups("")["facts_right"], 0)

    def test_found_values_are_reported_for_the_reader(self):
        found = score_several_lookups(PARTIAL)["found"]
        self.assertEqual(found["hospitality_mailbox"], "yes")
        self.assertEqual(found["lifeguard_mailbox"], "no")
        self.assertEqual(found["trainer_mailbox"], UNSTATED)


if __name__ == "__main__":
    unittest.main()
