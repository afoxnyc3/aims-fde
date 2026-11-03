# Real-ticket eval set (standard v0.3)

The eval behind the 2026-11-02 CTO demo ([deck](../../demo/tc4_demo.html)). The labels were made by IT against the role matrix (2026-10-07, owner: Business Development Manager), applied through standard v0.3.

**Real ticket text is held privately per org policy; labels and results are public.** `tickets.jsonl`, which has the ticket text behind `golden.jsonl`, is gitignored and never committed.

This set sits alongside the Week 1 goldens. `../run.py` and `../harness.py` do not read it, and the v0.3 standard and the agent that scores it are not in this repo yet.

## Files

| File | Rows | What it is |
| --- | --- | --- |
| `golden.jsonl` | 58 | Labels for 58 real, pseudonymized onboarding-queue tickets (`origin: real`, all `label_state: confirmed`). Split 29 dev / 29 test. Test: 13 `recommended`, 10 `human_review`, 6 `ignored`. Dev: 15 `recommended`, 6 `human_review`, 6 `ignored`, 2 `needs_information`. No ticket text |
| `grid.jsonl` | 181 | Synthetic scenario grid, 32 case types, ticket text generated, not real. Split 91 dev / 90 test. `label_state`: 160 synthetic by construction, 18 confirmed, 2 provisional, 1 needs ruling. The 2026-11-02 Hospitality Level 2 and Housekeeping rulings are applied (GRID-036, GRID-139, GRID-141) |
| `synthetic.jsonl` | 6 | Generated failures, split 3 dev / 3 test: a no-mailbox role with a blank personal email (2), missing job title, missing venue, a venue field that contradicts the notes, and an employee email equal to the manager's |
| `tickets.jsonl` | 58 | Private. Ticket text for `golden.jsonl`, joined on `ticket_ref`. Gitignored |

Fields in `expected`: `status`, `review_reason`, `missing_fields`, `role`, `system_login`, `system_role`, `venue`, `trainer_level`. The grid and synthetic files also have `contradiction`.

## Sanitized for this public repo

| Change | Why |
| --- | --- |
| Vendor and company terms made generic: the club-management system, its form labels (to the repo's existing `Account System` labels), payroll vendors (`Payroll Service`), the cross-club workspace, and the company-specific matrix name | Same norm as the rest of `use_case/` |
| Label keys renamed to `system_login` and `system_role` from the private pipeline's vendor-named keys | Same norm. Map them back before scoring with the private pipeline |
| Email domains: `company.com` to `example.com`, `gmail.com` to `example.net`, `yahoo.com` to `example.org` | Reserved domains. Distinct per source domain, so emails that were equal stay equal and emails that differed still differ |
| `golden.jsonl` evidence: 10 verbatim ticket excerpts removed, and 2 quoted off-matrix job titles redacted | Labels public, text private. The excerpts contained a pseudonymous email, the systems a requester named, and a contractor's firm |

## Results, as presented on 2026-11-02

From the [deck](../../demo/tc4_demo.html). The test split was run once:

- **24 of 29** right outcome, 95% CI 69–97%. 12 of 13 recommendations correct. **1 over-access case**: a lifeguard also covering fitness, where the matrix has no cross-unit rule.
- Synthetic gate: **84 / 84** on the held-back half of the grid, with 0 over-access.

The labels in this folder are newer than those results. In the deck, 14 test tickets were expected `recommended`; here it's 13. The Hospitality Level 2 ruling (BDM, 2026-11-02) moved TKT-14 to Hospitality Lead, `human_review` (`role_unmapped`). The agent recommended TKT-14 in the demo run, so scored against these labels that recorded output is a **second over-access case**, and the right outcomes become 23 of 29. The 24/29 has not been re-run on these labels.
