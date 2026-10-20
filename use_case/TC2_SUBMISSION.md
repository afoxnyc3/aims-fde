# TC2 submission

Synthetic onboarding tickets for an agent that recommends new-hire system access from a role standard, and a datasheet that says what they can and cannot prove. This page indexes each deliverable; the detail lives in the linked files.

**Loom:** [link]
**Branch:** `tc2-axes`

## Step 1: variation axes

Full definitions, rules and generator instructions: [`axes.md`](axes.md) (revision 6). Datasheet table: [`data/DATASHEET.md`](data/DATASHEET.md#variation-axes).

| Axis | Values | Real variation it covers |
| --- | --- | --- |
| Role fit | `exact` · `near_match` · `venue_dependent` · `outside_standard` (decline) | How cleanly a ticket's job title maps to a standard role, including title variants seen in real tickets and roles with no standard, which the agent must send to a person |
| Request intent | `new_hire` · `returning_or_moving` | Whether the person is new, or returning, transferring or promoted, which changes what may already exist |
| Data reliability | `clean` · `missing_required` · `internal_contradiction` · `changed_after_submission` | Whether the ticket can be trusted as filed: gaps, conflicting fields, and requester comments that change a detail after submission |
| Provisioning scope | `member_plus_staff_login` · `member_record_only` · `beyond_template` | What is asked for: the two jobs every ticket carries (member record, staff login), and requests beyond the standard template |
| Fixed rows | login problem · permission change · outage · offboarding · promotion via general request | Non-onboarding tickets the agent must leave alone |

Two axes are specific to this domain (role fit, provisioning scope); the decline value is `outside_standard`.

## Step 2: counts and settings

From [`data/DATASHEET.md`](data/DATASHEET.md#what-this-data-is):

| Count | Value |
| --- | --- |
| Planned | 126 |
| Generated | 125 (1 refused by the model, category `cyber`) |
| Schema-valid | 125 |
| After dedupe | 125 (0 dropped) |
| After the fifty-row read | 113 verified |
| Dead combinations | 13: 1 refused at generation, 11 cells whose only row was removed after the read, 1 fixed row that can't be submitted |
| Status mix (kept rows) | 36 recommended / 36 needs information / 36 human review / 5 ignored |

**Settings:** hosted `claude-opus-5-5` through the Anthropic API, effort low. **Temperature and top-p not set:** the model rejects both. Dedupe: character 5-gram Jaccard ≥ 0.85 within a cell, cross-cell pairs reported. Decision rows: dedupe threshold and generation model in [`decisions.md`](decisions.md) (Step 2 and Step 4 rows).

**Local comparison (optional):** `qwen3:4b` and `qwen3:8b` over a 3×3 temperature × top-p grid on a 24-row slice; results in [`gen/RUNLOG.md`](gen/RUNLOG.md).

## Step 3: leak check and fifty-row read

All four leakage boxes ticked by the reader; the read covered 50 stratified rows. **Removed (12):** 4 location-blank and 7 start-date-blank rows (both fields are required on the intake form), and 1 vague request that cannot be submitted. One line per row with its reason: [`data/DATASHEET.md`](data/DATASHEET.md#fifty-row-read-2026-10-20).

## Step 4: datasheet

[`data/DATASHEET.md`](data/DATASHEET.md): what it can validate, what it cannot validate (the real ticket mix, whether the labels are right, how missing information really looks, the promotion gate), what it must never be compared against, and the goldens provenance answer (unknown; the project owner decides). Model/endpoint decision: [`decisions.md`](decisions.md), Step 4 row.

## Step 6: shown to people who know the real data

Rows in [`stakeholders.md`](stakeholders.md); the decision it changed is the Step 6 row in [`decisions.md`](decisions.md).

- **Which would never happen:** in a blind read of 20 tickets (2026-10-19), a Technology Support Associate judged 4 unrealistic. The fifty-row read, with the Service Desk Manager's answers on required fields, removed 12 rows.
- **What comes in that isn't here:** Babysitting Associate and Babysitting Lead roles.
- **What would worry them if public:** read as the intake form being open to anyone: only managers should submit onboarding requests.
- **What changed:** the reviewer's stated rule on the largest policy question (Q7) contradicted their handling of the same tickets, so it moved to "needs reconciling" and v1 kept the provisional rule. No labels changed on unratified answers.

## Step 7: bring it to work

[`README.md`](README.md#bring-it-to-work): the project (AI-tool seat review blocked on analysing a sensitive chat export) and the three swap lines for data, model and approval.

## Not done

- **Step 5 (optional):** the Week 1 app was not pointed at a local model, so there is no `.env` diff or `ecosystem.md` plausibility line. The local models were used only for the generation comparison above.
