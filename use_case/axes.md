## Variation axes (revision 6)

> **Label provenance:** Labels are **computed by code** from the cell picks, the status rule, and the v0.1 reference tables below. The status rule and the tables are **not ratified** by the Service Desk; the open questions at the end could change roughly half the labels.

### Reference data (v0.1, draft)

**Standard role list (v0.1, draft)**

"Observed in requests" describes what requesters asked for on Region A onboarding tickets. It is **not** evidence of what the standard should be; the standard is unratified.

| Standard role | Department | System login (standard) | Observed in requests | Known title variants |
|---|---|---|---|---|
| Group Fitness Instructor | Group Fitness | YES, all clubs | Consistent | — |
| Personal Trainer | Personal Training | YES, all clubs | Consistent | level prefix ("Level 1 Personal Trainer") |
| Front Desk Associate | Front Desk | YES, all clubs | Consistent | legacy name ("Hospitality Associate"); level suffix ("Hospitality Associate Level 1") |
| Massage Therapist | Front Desk | YES, all clubs | No separate basis (grouped with Front Desk) | — |
| Membership Consultant | Membership Sales | YES, all clubs | Consistent, thin | — |
| Cafe Associate | Cafe | NO, all clubs | Consistent | — |
| Housekeeping Associate | Housekeeping | NO, all clubs | Consistent for non-managers | — |
| Lifeguard | Aquatics | By club (venue table) | Split, thin | — |
| Aquatics Lead | Aquatics | By club (venue table) | Split, thin | — |

**Clubs (placeholders only):** Club A, Club B, Club C, Club D, Club E. All Region A. Region B is out of scope for v1.

**Venue-dependent access (v0.1)**

| Role | Login required at | Login not required at |
|---|---|---|
| Lifeguard | Club C | Club A, Club B, Club D, Club E |
| Aquatics Lead | Club A, Club C | Club B, Club D, Club E |

**Outside-standard titles to rotate:** Carpenter, Special Events Assistant, Department Manager, Assistant General Manager, Foundation Coordinator, Babysitter.

### Who does what
| Step | Owner |
|---|---|
| Pick the cell, role, title variant, club, blanked field, contradiction variant, changed detail, comment timestamp, and the requester / manager / employee names and `@example.com` emails | **Code** (deterministic rotation, seeded) |
| Compute `expected_status`, `expected_proposal`, `expected_reason`, `expected_caveat` | **Code**, from the picks + status rule + v0.1 tables |
| Write the ticket text (form fields, notes, comments) from the picks | **Model** — returns ticket JSON only, no labels |
| Check the ticket contains every pick (exact title string, club, blank field actually blank, comment timestamp after creation, etc.) | **Code** — a row that fails is counted as a generation failure, not relabeled |

### Rules
1. **Conflict order:** each axis sets only its own fields; when instructions collide, Axis 3 > Axis 2 > Axis 4 > Axis 1.
2. **Blank job title:** every `exact` × `missing_required` row blanks the job title (6 cells). Those rows record `role_fit_observable: false`. All other `missing_required` rows rotate the blank across start date, location, and employee email, and `venue_dependent` never blanks location.
3. **Request vs. standard (all roles):** the role standard wins. `expected_proposal.login_required` comes from the standard role list (or the venue access table for by-club roles), never from the ticket's login field. When the ticket's login field disagrees with the standard, status stays `recommended` and `expected_caveat` = `request_differs_from_standard`. Under this rule, `member_plus_staff_login` and `member_record_only` rows for the same role produce the **same expected proposal** and differ only in the caveat. *(Open question 7.)* **The member record follows the ticket and is always created** (`expected_proposal.membership_required` is always true). *(Open question 8.)*
4. **Agree/disagree balance:** in every cell that can resolve to `recommended`, code alternates picks so the ticket's login field agrees with the standard on some rows and disagrees on others, starting on a different side per cell.
   - `exact`: alternate between login-YES roles and login-NO roles.
   - `venue_dependent`: alternate between login-required and not-required clubs. When `changed_after_submission` changes the club, code computes agree/disagree and `login_required` from the club **after** the change.
   - **`near_match` cannot alternate.** Observed near-match variants exist only for login-YES roles (Personal Trainer, Front Desk Associate), so `near_match` × `member_plus_staff_login` always agrees and `near_match` × `member_record_only` always disagrees. Agreement is confounded with scope in these cells, so **`near_match` results are not used as evidence for open question 7.**

### Axis 1: Role fit
Real variation: how cleanly the job title maps to a standard role.

| Value | Generator instruction (picks supplied by code) |
|---|---|
| `exact` | Use the picked title exactly as written in the standard role list, with its department. |
| `near_match` | Use the picked title variant. Code rotates three variants **observed in real tickets**: (a) level suffix, (b) level prefix, (c) legacy role name. |
| `venue_dependent` | Use the picked role (Lifeguard or Aquatics Lead) and the picked club in the location field. |
| `outside_standard` (calibrated decline) | Use the picked outside-standard title. It must not appear on the standard role list. |

### Axis 2: Request intent
| Value | Generator instruction |
|---|---|
| `new_hire` | Re-hire is NO and Previous Location is blank. |
| `returning_or_moving` | Re-hire is YES with the picked previous club, and a note says the person is returning, transferring, or being promoted (code picks which). |

### Axis 3: Data reliability
| Value | Generator instruction |
|---|---|
| `clean` | All required fields present and consistent. |
| `missing_required` | Leave the picked field blank (Rule 2). |
| `internal_contradiction` | Apply the picked variant: (a) location field names one club and the notes name a different club; (b) employee email identical to manager email. |
| `changed_after_submission` | Fill the form, then add a requester comment with the picked timestamp (after creation) changing the picked detail (start date or club) to the picked new value. The member record is never changed by a comment. |

### Axis 4: Provisioning scope
Every onboarding ticket carries two jobs: (1) a **member record** in the club-management system, which every employee gets and which hiring managers or People Ops have traditionally handled, and (2) a **staff login** with a role, which depends on the role. The prompt states both jobs explicitly; the form fields are `membership_required` (job 1) and `login_required` (job 2).

| Value | Generator instruction |
|---|---|
| `member_plus_staff_login` | Member record: YES. Staff login: YES. Nothing else requested. |
| `member_record_only` | Member record: YES. Staff login: NO. |
| `beyond_template` | Member record: YES. Staff login: YES. Plus a note requesting the picked extra (specific hardware, other named systems, or "same access as [named colleague]"). |

### Fixed rows (not crossed)
| # | Ticket | Expected status | Reason |
|---|---|---|---|
| 1 | Existing employee reports a login problem | `ignored` | Not an onboarding request |
| 2 | Permission change for an existing employee | `ignored` | Not an onboarding request |
| 3 | System outage or client won't open | `ignored` | Not an onboarding request |
| 4 | Offboarding request | `ignored` | Not an onboarding request |
| 5 | Promotion submitted as a general service request | `ignored` | Wrong channel: the agent acts only on onboarding request types. *Open question 3.* |
| 6 | Vague "I need my own account" with no role, club, or manager | `needs_information` | Possibly a real new hire; asking is safer than dropping it. |

Known limit: each fixed-row type is tested once.

### Status rule (provisional, applied by code)
First match wins.
1. Not an onboarding request → `ignored`
2. `missing_required` or `internal_contradiction` → `needs_information`
3. `outside_standard`, `returning_or_moving`, or `beyond_template` → `human_review`
4. Everything else → `recommended`

`failed` is not a ticket property; tested separately with forced tool errors.

### Stored per row (computed by code)
```json
{
  "cell_id": "venue_dependent|new_hire|clean|member_record_only",
  "axes": {"role_fit": "venue_dependent", "intent": "new_hire", "reliability": "clean", "scope": "member_record_only"},
  "picks": {"title": "Lifeguard", "club": "Club C", "near_match_variant": null, "blank_field": null,
            "contradiction_variant": null, "changed": null, "comment_ts": null},
  "expected_status": "recommended",
  "role_fit_observable": true,
  "expected_proposal": {"standard_role": "Lifeguard", "level": null, "club": "Club C",
                        "login_required": true, "membership_required": true, "extra_requests": []},
  "expected_caveat": "request_differs_from_standard",
  "expected_reason": null,
  "reference_versions": {"role_list": "v0.1", "club_access": "v0.1", "status_rule": "provisional-1"}
}
```

### Count and label mix
- Crossed grid: 4 × 2 × 4 × 3 = 96 cells.
- 12 `recommended` cells oversampled at 3 rows each (+24).
- Total: 96 + 24 + 6 fixed = **126 rows**.

| Status | Rows | Share |
|---|---|---|
| `recommended` | 36 | 29% |
| `needs_information` | 49 | 39% |
| `human_review` | 36 | 29% |
| `ignored` | 5 | 4% |

### Exclusions
- `venue_dependent` × `missing_required`: never blank location.
- Job title blanked only, and always, in `exact` × `missing_required`.
- Fixed rows never crossed.
- `changed_after_submission` never changes the member record: the changed detail is start date or club only, and `membership_required` is YES on every generated row.

### Implementation assumptions (made in `use_case/gen/`, not ratified)
Where this file is silent, the generator assumes the following. Each is a choice, not a Service Desk decision.
1. **`exact` uses the 7 fixed-login roles only** (Group Fitness Instructor, Personal Trainer, Front Desk Associate, Massage Therapist, Membership Consultant, Cafe Associate, Housekeeping Associate). Lifeguard and Aquatics Lead are by-club and belong to `venue_dependent`.
2. **`expected_proposal` and `expected_caveat` are set only on `recommended` rows.** Other rows carry `null` for both and a short `expected_reason` code (e.g. `missing_required:due_date`, `human_review:returning_or_moving+beyond_template`).
3. **The member record follows the ticket and is always created; the staff login follows the standard.** `expected_proposal.membership_required` is always true; `login_required` always comes from the role list or venue table (Rule 3). *(Revised in revision 6; earlier runs let a requester comment drop the membership.)*
4. **Rule 4's agree/disagree start side is staggered by scope as well as by cell**, so each scope gets a balanced split (3 agree / 3 disagree per role fit) rather than 4/2.
5. **Stored `picks` carry fields beyond the example above**: `standard_role`, `level`, `department`, `contradiction_club`, `extra_request`, `previous_club`, `intent_note`, `created`, `due_date`, `request_type`, and requester / manager / employee names and `@example.com` emails. Fixed rows carry a requester name; the three fixed rows about another employee (permission change, offboarding, promotion via general request) also carry that employee's name. Verification needs them to check a ticket against its picks.

### Removed, and why
| Removed | Reason |
|---|---|
| `duplicate` | Not detectable from one ticket; cross-ticket check runs before the agent. |
| Title-vs-department contradiction | Conflicts with `exact` / `near_match`. |
| Trailing-space, abbreviation ("PT"), plural near-matches | Trailing space doesn't survive parsing; "PT" collides with Part-time on the same form; plurals weren't observed in real tickets. |
| Notes under the trainer-level line as a "change" | No timestamp, so not evidence of a later change. Known parsing gap. |
| Model-written labels | Labels computed by code; the model writes ticket text only. |
| Wrong request type | Merged into fixed rows. |
| Intake form axis | Always moves with region in real data. |
| Region B empty form | Out of v1 scope. |
| Length, difficulty | Length doesn't vary on form tickets; difficulty follows from other axes. |

### Open policy questions for the Service Desk
| # | Question | Impact if answered differently |
|---|---|---|
| 1 | Rehire/transfer: `recommended` with caveat, or `human_review`? | 12 cells move |
| 2 | Missing info **and** role needs review: which comes first? | 36 cells swap labels |
| 3 | Fixed rows #5 and #6: right outcomes? | 2 rows |
| 4 | Who may change an onboarding detail after submission? (access-control decision; Service Desk lead, possibly IT/Security) | Adds a value once answered |
| 5 | Does trainer/associate **level** change access? | If yes, near-match variants (a) and (b) become distinct roles: ~2/3 of `near_match` rows relabel |
| 6 | Does access differ by club for roles beyond Lifeguard and Aquatics Lead? | Expands the venue access table |
| 7 | When the ticket's login request disagrees with the role standard, provision per standard with a caveat, or treat as a contradiction? | ~18 of 36 `recommended` rows (the disagreeing half across `exact`, `near_match`, and `venue_dependent`) would move to `needs_information` or `human_review`. Largest single swing on the recommended set. |
| 8 | Is member-record creation in scope for the agent, or redirected to People Ops? Owner: project owner, with People Ops. | All `member_record_only` rows: 44 rows across 32 cells. |
| 9 | Who files offboarding, promotions and transfers: the hiring manager, People Ops, or both? The Service Desk Manager says managers; the Technology Support Associate says People Ops for offboarding and promotions. Owner: Service Desk Manager, with People Ops. | Decides whether manager-filed promotion and offboarding tickets (fixed rows 4 and 5, the "promoted" intent) are realistic, and whether a People Ops requester axis is needed. |

- Evidence behind Q6: the venue access table rests on 6 aquatics tickets (3 YES / 3 NO). Ask: is login by club a real rule, or did managers fill the field inconsistently?

**Service Desk input, 2026-10-19 (Technology Support Associate; unratified, no decider named).** Labels do not change until an answer is ratified.

| # | Stated answer | Matches the blind-read practice? | Status |
|---|---|---|---|
| 1 | Recommend, with a note to check the existing account | Yes (tickets 5, 6, 7 processed) | Recorded; pending ratification |
| 2 | Send for review first | No (ticket 9: "membership only no login") | Needs reconciling with the decider |
| 3 | Not decided | — | Open. Fixed row 6 (vague request) was removed from v1 after the fifty-row read: with no required field filled, it cannot be submitted through either form |
| 4 | Requester or listed manager only | Matches the current rule | Access-control decision; pending the security owner |
| 5 | Same access at every level | Yes; matches the current assumption | People Ops' role matrix (2026-10-07) agrees: Level 1–4 Trainers get the same access. Unratified |
| 6 | One rule per role everywhere (rule not stated) | Tickets 12 and 13 suggest lifeguards get a login everywhere | People Ops' role matrix (2026-10-07) agrees: Lifeguard and Aquatics Lead get a login at every club, so the venue table above is likely wrong. Unratified |
| 7 | Treat as a contradiction and ask the requester | No (processed 2, 3, 4, 13; login per role on 12) | Needs reconciling with the decider |
| 8 | Not asked (added in revision 6) | — | Open |
