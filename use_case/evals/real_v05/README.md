# real_v05: the TC5 label set and runs (2026-11-10)

Same 58 real tickets (29 dev, 29 test) and the same synthetic grid as [`../real_v03`](../real_v03/README.md). Ticket text stays private; labels and structured results are public, with the same redactions.

`real_v03` is frozen as the TC4 record: its saved runs were scored against those labels, and `run.py --committed` refuses to rescore a saved recommendation against a changed label. TC5's label changes therefore live here, and the TC5 runs are scored against these labels only.

## What changed from real_v03

| Change | Tickets | Source |
| --- | --- | --- |
| `system_role` renamed from v0.3 names that do not exist in the account system to the production role | 16 (dev 9, test 7) | Rulings 2026-11-10, below |
| TKT-293 `recommended` -> `needs_information` (`person_name`) | 1 (dev) | Owner surname policy (2026-11-07); this ticket gives a one-word name and was missed in the 11-07 relabel |

Role-name rulings (2026-11-10), by role:
- Front Desk Associate -> **Hospitality Associate** (project owner confirmed).
- Membership Consultant -> **Sales Associate**, per club (Technology Support Associate, desk practice).
- Lifeguard -> **Hospitality Associate**, at the Fitness business unit (Technology Support Associate).
- Massage Therapist -> **Personal Trainer/Pro New**, plus the Massage Therapist staff group per club (project owner; production census agrees).
- Personal Trainer -> **Personal Trainer/Pro New** (the v0.3 name was the legacy role).
- NY Group Fitness Instructor -> **Senior Group Fitness Instructor** (current SOP; owner-approved exception to the staff-admin hard stop, see `decisions.md`).

No status label changed except TKT-293. Grid labels are unchanged.

## Results (standard v0.5, current agent)

| Split | Right outcome | Over-access | Run |
| --- | --- | --- | --- |
| test | 27 of 29 (0.93) | 0 | `results/endpoint_test.json` |
| dev | 28 of 29 (0.97) | 0 | `results/endpoint_dev.json` |
| grid (synthetic) | 174 of 180 (0.97) | 2 | `results/endpoint_grid.json` |

**Not held out.** The test split has now been read closely several times, and the systems-beyond-the-bundle check was added after a test run on v0.5 showed the two TC4 over-access tickets were still recommended. Read test as "same tickets, current agent". Dev and the grid carry the evidence; a fresh held-out set is the gate before production.

## Provenance notes

- **Evidence text is carried over from real_v03.** For the 16 renamed rows, `evidence` still quotes the v0.3 mapping (for example "Front Desk Associate"). The `expected` fields are the v0.5 labels above; the evidence records where the original label came from.
- **Run metadata says `"labels": "use_case/evals/real_v03"`.** The private runner kept the label path of the set it read, and applied the TC5 changes as an overlay. The `expected` block inside every result row matches `real_v05/golden.jsonl` exactly, and the counts recompute from these files (checked in a second, independent review of PR #58).
- **Code after the runs:** three review fixes landed after these runs (validation of new standard keys, dotted system names, and the approver for a system request next to marketing "promotion" text). None changes a status on these tickets: the system-name matches on all 58 real tickets and the grid are identical before and after.
