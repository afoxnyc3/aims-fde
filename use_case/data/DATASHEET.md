# Datasheet

## What this data is

**Generated on:** 2026-10-20 (run `synth_run_20261020_113825`, saved as `synthetic_v1.jsonl`)
**Generated from:** the ticket schema in `gen/generate.py` and the written description in [`axes.md`](../axes.md) (revision 6): axes, rules, the draft v0.1 role list and venue table. No real ticket was used as a seed. Code picks every axis value, name, date and club, and computes every label from the picks and the provisional status rule. The model writes ticket text only.
**Business unit and form:** the fitness business unit files onboarding requests through an HR intake form; other business units use the service portal's onboarding form, which requires different fields. v1 models the fitness form only, per the Service Desk Manager (2026-10-20).
**Rows:** 126 planned · 125 generated · 125 schema-valid · 125 verified · 125 after dedupe · **113 after the fifty-row read** · 13 dead combinations

| Count | Value | Note |
| --- | --- | --- |
| Planned | 126 | 96 crossed cells, 12 `recommended` cells oversampled to 3 rows, 6 fixed rows |
| Generated | 125 | 1 row refused by the model's safety screen (category `cyber`), twice |
| Schema-valid | 125 | Validated against the `Ticket` pydantic model |
| Verified | 125 | Each ticket contains its picks (`gen/verify.py`); not a plausibility check |
| After dedupe | 125 | 0 dropped: character 5-gram Jaccard ≥ 0.85 within a cell; same-cell max 0.38 |
| Removed after reading | 12 | 11 rows blank a field the fitness form requires (4 location, 7 start date), plus the vague account request (fixed row 6), which cannot be submitted. See "Fifty-row read" below. |
| **In the file** | **113 verified** | `synthetic_v1.jsonl` holds 114 rows: the 113 verified plus the refused row (`verified: false`). Removed rows are kept locally in `synthetic_v1_removed.jsonl` with their reasons. |
| Dead combinations | 13 | 1 refused (`outside_standard` × `new_hire` × `internal_contradiction` × `beyond_template`; the refusal follows one pick combination, employee email = manager email plus email-system access, not the cell); 11 `missing_required` cells whose only row was removed after reading; fixed row 6. |
| Verified status mix | 36 / 36 / 36 / 5 | recommended / needs_information / human_review / ignored, after reading (before reading 36 / 48 / 36 / 5; planned 36 / 49 / 36 / 5) |

**Settings:** hosted `claude-opus-5-5`, effort `low`, structured output through a strict tool schema. **Temperature and top-p: not set.** The model rejects both, so the run used the provider's default sampling. Pick seed 42. Dedupe: character 5-grams over field values, notes and comments, Jaccard ≥ 0.85, within the same cell only. Local `qwen3:4b` and `qwen3:8b` temperature × top-p grids were run on a 24-row slice for comparison; they are not part of this file (see [`gen/RUNLOG.md`](../gen/RUNLOG.md)).

**Known generation artifact (found in the fifty-row read, 2026-10-20):** the notes in all 120 crossed rows tend to repeat the generation prompt's wording, "member record" and "staff login". Revision 6 added both terms to the prompt to state the ticket's two jobs; real tickets use the form's own labels, such as "Membership Required" and "Account System Login Required". The note text is therefore more uniform and less realistic than real tickets. The 6 fixed rows are not affected. Kept as is for v1; the fix (asking for the form's own terms in notes) is planned for revision 7.

## Variation axes

Full definitions, generator instructions, and rules: [`use_case/axes.md`](../axes.md) (revision 6).

| Axis | Values |
| --- | --- |
| Role fit | `exact` · `near_match` · `venue_dependent` · `outside_standard` (calibrated decline) |
| Request intent | `new_hire` · `returning_or_moving` |
| Data reliability | `clean` · `missing_required` · `internal_contradiction` · `changed_after_submission` |
| Provisioning scope | `member_plus_staff_login` · `member_record_only` · `beyond_template` |
| Fixed rows (not crossed) | login problem · permission change · outage · offboarding (all `ignored`) · promotion via general request (`ignored`) · vague account request (`needs_information`) |

## What it can validate

These rows test whether the agent classifies onboarding tickets the way the draft rule says it should. The labels follow the draft rule, not what the Service Desk actually does, so a score on this data measures agreement with the draft rule, nothing more.

Within that limit, the 113 verified rows cover all four outcomes (recommended, needs information, human review, ignored) and every axis value: exact, near-match, venue-dependent and outside-standard titles; new hires and returning or moving employees; clean tickets, internal contradictions and late changes; and requests inside and beyond the standard template. So the data can show whether the agent recognises each of those cases and routes it to the outcome the draft rule assigns.

"Verified" means each ticket contains what it was generated to contain. It does not mean the ticket is realistic.

## What it cannot validate

**The real mix of tickets.** About 60% of real tickets tagged for the club-management system are permission changes and app or scanner problems; in this data they are 5 of 113 rows. Only the fitness business unit's intake form is modelled, and roles that do come in, such as Babysitting Associate and Lead, are missing. A score here says nothing about how the agent performs on the traffic it will actually see.

**Whether the labels are right.** Every label follows a draft rule nobody has ratified. People Ops' role-by-access matrix already contradicts it: Lifeguard and Aquatics Lead get a login at every club, not by club, and the draft standard's role names differ from the matrix's. The Service Desk's stated answers also differ from what they did with the same tickets (Q7, Q2). A high score can mean the agent faithfully reproduces a wrong rule.

**How missing information really looks.** The fitness form requires location and start date, so a ticket can't arrive with those blank; the 11 rows that tested blanks were removed after reading. On real tickets, missing or wrong information probably shows up as placeholders, tentative dates or contradictory free text, which this data never generates. The agent's handling of real incomplete tickets is untested.

**The promotion gate.** Nothing yet. The gate is meaningless until a role's standard is ratified. It is meant to work like this: for one role, run a batch of synthetic tickets (for example 200) through the pipeline. If at least 95% come back recommending the right role and access, with "right" meaning the ratified standard as confirmed by the Service Desk, the role can move from a recommendation posted as a Jira comment to automation. Until the standard is ratified, a 95% score here only shows agreement with a draft that is already known to be wrong for some roles. Synthetic accuracy shows the pipeline reads generator-style tickets; the live-ticket route (90% over 20 live tickets) is what shows it reads real ones.

## What it must never be compared against

The real answer will be the ratified role standard: for each role, the exact permissions it receives. That doesn't exist yet. Until it does, the onboarding ticket is the source for **which role** a new hire has, and the draft standard is a placeholder for **what that role gets**. Neither these synthetic rows nor historical grants are ground truth: historical grants contain the drift this project exists to fix.

So accuracy on this data must never be reported as accuracy on real tickets, and these labels must never be scored against what was historically granted, as if either were the ratified standard.

## Leakage check — outward (what left)

- [x] No real record was used as a seed.
- [x] No real entity names, IDs, or identifiers appear.
- [x] No distinctive internal formats that would identify the firm.
- [x] Rare categories were generated, not copied.

*Ticked by the reader (2026-10-20). The first box reflects how the data was made: v1 was generated from `axes.md` and the schema, not from the goldens or any real ticket. The other three follow the fifty-row read, which also confirmed "nothing here would embarrass us in a public repo".*

### Fifty-row read (2026-10-20)

**What was read:** 50 rows drawn from `synthetic_v1.jsonl` (11 per role fit plus all 6 fixed rows, covering every reliability and scope value); 49 marked. 16 were read in full and discussed; the rest were skimmed for title, location and notes. **What was looked for:** tickets that could not happen, prompt wording copied into tickets, misplaced sign-offs, fields the picks don't call for, notes that contradict the form, and anything that would identify the firm. **Result:** keep 39 · remove 4 · unsure 6 on the page; no leak concerns. Form requirements confirmed with the Service Desk Manager then removed every row with the same flaw, not only the ones on the page.

**Removed, and why** (one line per row):

| Row | Reason |
| --- | --- |
| `near_match\|new_hire\|missing_required\|member_record_only#0` | Location blank; Location is required on the fitness form |
| `near_match\|returning_or_moving\|missing_required\|member_record_only#0` | Location blank; Location is required on the fitness form |
| `outside_standard\|new_hire\|missing_required\|member_record_only#0` | Location blank; Location is required on the fitness form |
| `outside_standard\|returning_or_moving\|missing_required\|member_record_only#0` | Location blank; Location is required on the fitness form |
| `near_match\|new_hire\|missing_required\|member_plus_staff_login#0` | Start date blank; Target Date (the start date) is required on the fitness form |
| `near_match\|returning_or_moving\|missing_required\|member_plus_staff_login#0` | Start date blank; required on the fitness form |
| `venue_dependent\|new_hire\|missing_required\|member_record_only#0` | Start date blank; required on the fitness form (kept on the page with "needs a start date"; superseded by the required-field rule) |
| `venue_dependent\|returning_or_moving\|missing_required\|member_plus_staff_login#0` | Start date blank; required (kept on the page; superseded) |
| `venue_dependent\|returning_or_moving\|missing_required\|beyond_template#0` | Start date blank; required (kept on the page; superseded) |
| `outside_standard\|new_hire\|missing_required\|member_plus_staff_login#0` | Start date blank; required on the fitness form |
| `outside_standard\|returning_or_moving\|missing_required\|member_plus_staff_login#0` | Start date blank; required (marked unsure on the page for a different reason: a carpenter would not get a staff login) |
| `fixed\|6#0` (vague account request) | Could not be submitted: none of the required fields on either form are filled |

**Kept with a flag:** `outside_standard|returning_or_moving|missing_required|beyond_template#0` (Foundation Coordinator): "foundation employees do not get access to staff app"; a manager might still ask, which is what `human_review` is for. **Still pending:** 6 rows with a blank job title (Rule 2) stay until it is confirmed whether Position Title is required on the form's new-hire topic.

## Leakage check — inward (what the eval shares with the training data)

**Are the goldens disjoint from anything the system was, or will be, tuned on?**
**Unknown.** The six goldens were hand-written in TC1, modeled on real fitness onboarding tickets. Whether those source tickets will ever feed the agent's prompt, a retrieval corpus (Week 3) or a fine-tuning set (Week 8) is not yet decided. The project owner decides, and the answer will be recorded in `decisions.md` before any of those steps uses real tickets.

**Overlap between `golden.jsonl` and this file, by the dedupe measure:** 0 pairs at Jaccard ≥ 0.85 (character 5-grams over variable content, with the goldens' form labels stripped). The closest golden-to-row similarity is 0.13 (DEMO-001).
