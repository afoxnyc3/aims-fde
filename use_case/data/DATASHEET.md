# Datasheet

<!-- Written in TC2, alongside your synthetic data. This file is committed; the
     data itself is not. -->

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

<!-- What you varied to get coverage: persona, format, difficulty, edge cases. -->

Full definitions, generator instructions, and rules: [`use_case/axes.md`](../axes.md) (revision 6).

| Axis | Values |
| --- | --- |
| Role fit | `exact` · `near_match` · `venue_dependent` · `outside_standard` (calibrated decline) |
| Request intent | `new_hire` · `returning_or_moving` |
| Data reliability | `clean` · `missing_required` · `internal_contradiction` · `changed_after_submission` |
| Provisioning scope | `member_plus_staff_login` · `member_record_only` · `beyond_template` |
| Fixed rows (not crossed) | login problem · permission change · outage · offboarding (all `ignored`) · promotion via general request (`ignored`) · vague account request (`needs_information`) |

## What it can validate

<!-- YOURS TO WRITE. Delete this comment when done. Evidence to draw on:
- Every crossed axis combination appears at least once (95 of 96 cells verified); labels are computed by code, so each row's expected outcome is exactly what the provisional rule says.
- 125 of 126 tickets verifiably contain their picks: exact titles, blanked fields, contradictions, timestamped changes, extra requests.
- The decline path (outside_standard) and the needs_information / human_review / ignored branches all have rows.
- So the narrow claim: whether the pipeline applies the PROVISIONAL rule correctly to tickets shaped like these, per axis value. -->

## What it cannot validate

<!-- YOURS TO WRITE: the graded judgement, in your words, at least three things specific to this data. Delete this comment when done. Evidence to draw on:
- Real distribution: your profiling of 257 tickets found about 60% of tickets tagged for the club-management system are permission changes and app or scanner problems; here they are 6 of 126 rows (fixed rows, one each).
- Labels follow an unratified provisional rule. Pending Service Desk input would move about 18 of 36 recommended rows (Q7), 12 cells (Q1) and 36 cells (Q2); the reviewer's stated rule and practice disagreed on Q7 and Q2.
- The v0.1 role standard is thin: the venue table rests on 6 aquatics tickets (3 YES / 3 NO).
- Plausibility: verification proves a ticket contains its picks, not that it is realistic. The Service Desk judged 4 of 20 revision-5 tickets unrealistic (8, 11, 17, 18).
- One model wrote every ticket, at default sampling: one writing style; revision 6 notes echo the prompt's two-jobs wording.
- Not generated at all: Region B empty forms, comp-membership conversions, member-only requests from People Ops (Q8), batch hires, duplicates (removed by design).
- A realistic ticket shape is missing: the model refuses one combination, so that cell has no row.
- Real ticket text carries sensitive content (credentials, personal contact details, compensation, member identifiers) that synthetic text does not, so masking and leakage behaviour cannot be tested here.
- From the fifty-row read and the Service Desk Manager (2026-10-20): every crossed row signs the notes with a requester who is not the listed manager, but on the fitness form the requester is always the hiring manager. Transfer and promotion rows ask for a new member record, which an existing employee already has. Fixed rows carry onboarding fields that IT help and other Jira request types don't have. Front-desk roles show department "Front Desk" where real tickets say "Hospitality". Change comments reuse identical wording and ISO dates.
- People Ops' role-by-access matrix (dated 2026-10-07, internal, not in this repo) disagrees with the draft standard: Lifeguard and Aquatics Lead get a login at every club (the venue table says by club), the current title is "Hospitality Associate" (the draft calls it a legacy variant), and several "outside-standard" titles are real roles in the matrix. Babysitting Associate and Lead are missing from v1.
- Intake varies by who you ask: the Technology Support Associate says offboarding and promotions come from People Ops; the Service Desk Manager says managers file them. v1 generates every ticket as manager-filed.
- Coverage shrank after reading: 11 `missing_required` cells have no row, because the form requires the fields they blank. Missing information on real fitness tickets would look different (placeholders, wrong values, free text).
- Consider: the promotion gate in decisions.md uses accuracy on synthetic tickets per role. Say what that gate can and cannot rest on while these labels are unratified. -->

## What it must never be compared against

<!-- YOURS TO WRITE. Delete this comment when done. Evidence to draw on:
- Real ground truth lives in the onboarding ticket history (Jira Service Management) and the role assignments actually recorded in the club-management system. Product (the Senior Product Manager) and IT administer them.
- decisions.md already says historical grants are not ground truth either: they contain the variance the project exists to resolve.
- So: accuracy on these rows must never be reported as accuracy on real tickets, and these labels must never be scored against historical grants as if either were the ratified standard. -->

## Leakage check — outward (what left)

- [ ] No real record was used as a seed.
- [x] No real entity names, IDs, or identifiers appear.
- [x] No distinctive internal formats that would identify the firm.
- [x] Rare categories were generated, not copied.

*Ticked by the reader after the fifty-row read (2026-10-20), which also confirmed "nothing here would embarrass us in a public repo". The first box describes how the data was made; tick it yourself if you agree.*

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
<!-- YOURS TO ANSWER: yes, disjoint | no — overlap: <which goldens, which source> | unknown — who would know: <role>. Evidence: the six goldens were hand-written in TC1, modeled on real onboarding ticket patterns; the question is whether those same real tickets will ever feed a prompt, retrieval or fine-tune. -->

**Overlap between `golden.jsonl` and this file, by the dedupe measure:** 0 pairs at Jaccard ≥ 0.85 (character 5-grams over variable content, with the goldens' form labels stripped). The closest golden-to-row similarity is 0.13 (DEMO-001).
