<!--
The draft access standard as retrieval pages. Copied from use_case/axes.md
(revision 6, reference data v0.1) so the container carries it; that file stays
the source. corpus.py turns each `## STD-...` section into one page, named by
its first word. Synthetic and unratified: placeholders for the real standard.
-->

## STD-role-list Standard role list (v0.1, draft)

Which standard roles exist, their department, and whether the role gets a staff
login in the club-management system. Every employee also gets a member record.
"Observed in requests" is what requesters asked for on onboarding tickets, not
evidence of what the standard should be. The standard is unratified.

| Standard role | Department | System login (standard) | Observed in requests | Known title variants |
|---|---|---|---|---|
| Group Fitness Instructor | Group Fitness | YES, all clubs | Consistent | none |
| Personal Trainer | Personal Training | YES, all clubs | Consistent | level prefix ("Level 1 Personal Trainer") |
| Front Desk Associate | Front Desk | YES, all clubs | Consistent | legacy name ("Hospitality Associate"); level suffix ("Hospitality Associate Level 1") |
| Massage Therapist | Front Desk | YES, all clubs | No separate basis (grouped with Front Desk) | none |
| Membership Consultant | Membership Sales | YES, all clubs | Consistent, thin | none |
| Cafe Associate | Cafe | NO, all clubs | Consistent | none |
| Housekeeping Associate | Housekeeping | NO, all clubs | Consistent for non-managers | none |
| Lifeguard | Aquatics | By club (see STD-venue-access) | Split, thin | none |
| Aquatics Lead | Aquatics | By club (see STD-venue-access) | Split, thin | none |

Clubs: Club A, Club B, Club C, Club D, Club E (all Region A; Region B is out of
scope). Titles not on this list are outside the standard, for example Carpenter,
Special Events Assistant, Department Manager, Assistant General Manager,
Foundation Coordinator and Babysitter.

## STD-venue-access Venue-dependent access (v0.1, draft)

Two roles get a staff login at some clubs and not others. For these roles the
club decides the login, not the role alone.

| Role | Login required at | Login not required at |
|---|---|---|
| Lifeguard | Club C | Club A, Club B, Club D, Club E |
| Aquatics Lead | Club A, Club C | Club B, Club D, Club E |

When a late comment changes the club, the login follows the club after the
change.

## STD-status-rule Status rule and request-vs-standard rule (provisional)

How an onboarding ticket is routed. First match wins.

1. Not an onboarding request (login problem, permission change, outage,
   offboarding), or a promotion filed as a general request (wrong channel):
   `ignored`.
2. A required field is missing (job title, employee email), or the ticket
   contradicts itself (location and notes name different clubs; employee email
   equals manager email): `needs_information`.
3. Title outside the standard, a returning, transferring or promoted employee,
   or a request beyond the standard template (specific hardware, other named
   systems, "same access as" a colleague): `human_review`.
4. Everything else: `recommended`.

The role standard wins over the request. The staff login comes from the
standard role list (or the venue table for by-club roles), never from the
ticket's login field. When the two disagree the ticket is still `recommended`,
with the caveat `request_differs_from_standard`. The member record follows the
ticket and is always created. Both rules are provisional (open questions 7 and
8 with the Service Desk).
