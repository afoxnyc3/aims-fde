# Generator run log

One entry per run. The data stays in `use_case/data/` (gitignored); this file
records what was run and what happened. Newest last.

## 2026-10-18 — small batch, run 1 (`synth_run_20261018_200802`)

- **Scope:** `--role-fit venue_dependent --one-per-cell` (24 rows, 24 cells), seed 42.
- **Model:** `claude-opus-5-5`, Anthropic backend, effort `low`.
- **Temperature:** requested 0.7, **not applied**. The model rejects the parameter (400: "`temperature` is deprecated for this model"), so generation ran at the model's default sampling.
- **Result:** 24 planned, 21 generated, 21 schema-valid, **17 verified**, 7 dead cells.
- **Failure causes:**
  - 3 rows, generator bug: four parallel workers sent `temperature` before the first 400 switched it off, and only the first worker retried. The other three rows were recorded as errors, not generated. Fixed: any request that carried `temperature` retries without it.
  - 3 rows, verifier too strict: notes said "coming back to the company" for `returning`, but the check only accepted the stem `return`. Fixed with an accepted-phrase list.
  - 1 row, real generation failure: a `transferring` row left `previous_location` blank.

## 2026-10-18 — small batch, run 2 (`synth_run_20261018_200858`)

- **Scope, model, temperature:** same as run 1 (temperature not applied).
- **Result:** 24 planned, 24 generated, 24 schema-valid, **24 verified**, 0 dead cells. Dedupe skipped (one row per cell).
- **Read-through notes:** on the contradiction-b row, the model explained the shared email in the notes ("I put mine for now"). Manager names repeated across rows. Both led to the next change set: a no-explanation instruction on contradiction rows, and code-picked names.

## 2026-10-18 — small batch, run 3 (`synth_run_20261018_221801`)

After commit `8dfbf03` (code-picked names, membership exclusion, no-explanation instruction on contradiction rows, accepted-phrase list for the intent note).

- **Scope, model, temperature:** same as run 1 (temperature not applied).
- **Result:** 24 planned, 24 generated, 24 schema-valid, **24 verified**, 0 dead cells. Dedupe skipped (one row per cell).
- **Spot check:** none of the 3 contradiction-b rows explains the shared email. The 2 `membership_only` × `changed_after_submission` rows change start date and club, not membership.

## 2026-10-18 — full run (`synth_run_20261018_221844`)

- **Scope:** all 126 rows (102 cells), seed 42. Same model; temperature not applied.
- **Result:** 126 planned, 125 generated, 125 schema-valid, **125 verified**. After dedupe: 125 (0 dropped at Jaccard ≥ 0.85, 0 cross-cell pairs).
- **Dead cell:** `exact|new_hire|internal_contradiction|beyond_template`. Its only row was `schema_invalid` after one retry. The raw model output was not kept, so the cause is unknown.
- **Verified status mix:** 36 recommended / 48 needs_information / 36 human_review / 5 ignored (planned 36/49/36/5).
- **Intent phrases matched:** returning → "coming back" 9, "returning" 7; transferring → "transferring" 16; promoted → "promoted" 16.
- **Dedupe calibration:** highest same-cell Jaccard was 0.43 (mean 0.22, 36 pairs). Code-picked names, emails, and dates are part of the shingled content, so same-cell rows sit far below 0.85. Per the decisions.md rule, this is a signal to lower the threshold or exclude code-picked values from the shingles. Not yet decided.

## 2026-10-18 — full run, repeat (`synth_run_20261018_224510`)

Re-run to fill the dead cell, after `generate.py` started keeping the raw model reply on every failed attempt (`failed_attempts`).

- **Scope, model, temperature:** as the previous full run (temperature not applied).
- **Result:** 126 planned, 125 generated, 125 schema-valid, **125 verified**. After dedupe: 125 (0 dropped; same-cell Jaccard max 0.43, mean 0.21).
- **Dead cell, same as before:** `exact|new_hire|internal_contradiction|beyond_template`. Cause now recorded: both attempts returned `stop_reason: "refusal"` with no content. **This is not a schema failure.**
- **Diagnosis (one extra call per variant, so single samples):**
  - As generated: refused, category `cyber`. That makes 5 refusals in 5 tries across the two runs and this test.
  - Same row without "Do not explain, justify, or acknowledge the inconsistency.": generated normally.
  - Same row with a hardware extra request instead of "access to the marketing email tool": generated normally.
  - Reading: the refusal comes from a combination. The new account uses the manager's email (contradiction b), asks for access to an email system, and the prompt says to hide the inconsistency. Together these read as covert account takeover. No single instruction triggers it on its own.
- **Decision (2026-10-18):** the cell is left dead, with the cause recorded above. Running the frontier model first showed one of its limits as a synthetic-data generator: its safety classifier refuses a realistic ticket shape. Next runs move to local models, where temperature and top-p can be set.

## 2026-10-18 — local trial, `qwen3:4b`, base setting (`sweep_qwen3-4b_base_20261018_235625`)

First run of `sweep.py`: local model through LiteLLM → Ollama 0.40.6, with temperature and top-p applied.

- **Slice:** 24 rows, one per cell: `venue_dependent` × `new_hire` (12) and `outside_standard` × `new_hire` (12). Seed 42 for picks. Per-row sampling seed is derived from `row_id`, so it is the same across settings and models.
- **Model:** `ollama_chat/qwen3:4b`, digest `359d7dd4bcda`. `git 70f17d9`.
- **Settings:** temperature 0.7, top-p 0.8 (Qwen3 model card, non-thinking mode: *looked up*). `top_k` 0, `repeat_penalty` 1.0, `num_ctx` 8192, `think` false. LiteLLM's request body to Ollama was inspected: all six options arrive in `options`, and `think` arrives top-level. top-k 0 = no limit relies on llama.cpp semantics (`ollama ps` shows the llamacpp runner).
- **Result:** 24 generated, 0 unparseable, 0 schema-invalid, 24 schema-valid, **23 verified**, 1 dead cell. After dedupe 23, by construction (one row per cell per setting). Highest cross-cell similarity 0.61 (masked text); none at or above 0.85.
- **Dead cell:** `venue_dependent|new_hire|internal_contradiction|beyond_template`. The model put the requester sign-off in a comment instead of the notes, so verification failed on `names` and `changed` (unexpected comment). This is a real generation miss.
- **Echo (prompt wording copied into the ticket):** 4 rows, all `beyond_template`, with "no other club(s)" taken from the prompt's "Mention no other club." **3 of the 4 passed verification.** Verification proves a ticket contains its picks, not that it reads as plausible. The echo check (`echo_ngrams`) was tuned on this file: it flags exactly these 4 rows and nothing else. Exclusions: code-picked values masked (label fields such as `changed.detail` are not treated as values), mandated phrases masked, stopword-only 3-grams dropped, crude plural fold. It may need retuning when it meets other settings.
- **Timing (*measured*, run alone):** warm-up 5.5 s; median 5.7 s per ticket (range 5.3–7.1); 152 s wall-clock for 24 rows.
- **Failure paths:** `sweep.py --selftest` feeds `classify()` a non-JSON reply and a dict missing required fields. It asserts `unparseable` and `schema_invalid`, and that both records serialize. Passes. No model call.

## Fifty-row read checklist (additions)

Beyond the datasheet's leakage boxes, look for:
- [ ] **Prompt-wording echo:** instruction text copied into notes or comments ("no other club", "use those words", "exactly"). The `echo` flag catches the known pattern, not every phrasing.
- [ ] **Sign-off placement:** the requester's sign-off in the notes, not in a comment.
- [ ] **Fields the picks don't call for:** for example `trainer_level` or `specialties` filled for non-trainer roles (seen on an Aquatics Lead in the 4B smoke test). `verify.py` does not check these.
- [ ] **Notes that contradict the form:** for example a `membership_only` ticket (login NO) whose note says the person "will need access to the club-management system" (seen in the 8B base trial). Neither `verify.py` nor the echo check compares notes against form fields.

## 2026-10-19 — fixed rows regenerated with code-picked employee names (`synth_run_20261019_001640`)

- **Why:** in the 126-row run, fixed rows code-picked only the requester, so the model invented the employee. Row `fixed|5` (promotion via general request) came back as "Priya Lindqvist". The name is fictional, but Priya is also the course notebooks' persona.
- **Change:** `picks.py` now code-picks an employee name and email for the fixed rows that concern someone other than the requester (`permission_change`, `offboarding`, `promotion_general`). `generate.py` passes the name in, and `verify.py` checks the employee is named in the summary or notes. Added a `--fixed-only` filter.
- **Side effect:** names come from one seeded rotation, so requester names for fixed rows 2–6 shifted. The 120 crossed rows are unchanged, and the plan still asserts 126 rows with the 36/49/36/5 mix. Fixed-row tickets in earlier run files no longer match the current picks; each stored row keeps the picks it was generated from.
- **Re-pick:** `fixed|5` employee is now Vesper Yarrowby (requester Tobias Copperfield).
- **Result:** 6 planned, 6 generated, 6 schema-valid, **6 verified**. Model `claude-opus-5-5`; temperature not applied.
- **Use:** `use_case/data/review_20.md` takes its two fixed rows (#5 and #6) from this file and all other rows from `synth_run_20261018_221844`.

## 2026-10-19 — full grids, `qwen3:4b` and `qwen3:8b` (`sweep_qwen3-4b_grid_20261019_000744`, `sweep_qwen3-8b_grid_20261019_002506`)

- **Grid:** temperature {0.2, 0.7, 1.0} × top-p {0.5, 0.8, 0.95}, the same 24-row slice, per-row seed from `row_id`. `top_k` 0, `repeat_penalty` 1.0, `num_ctx` 8192, `think` false. Both files share the same 24 `prompt_sha` values, so the prompts are byte-identical. The 4B ran at `git 2718b05` and the 8B at `8498faf` (the change only touched fixed rows).
- **Schema:** 432 of 432 calls parsed and validated (0 unparseable, 0 schema-invalid). Under Ollama's schema-constrained decoding, those two counters do not vary, so `verified` is the count that moves.
- **Verified per setting** (out of 24):

  | T \ top-p | 0.5 | 0.8 | 0.95 |
  |---|---|---|---|
  | 4B @ 0.2 | 24 | 24 | 24 |
  | 4B @ 0.7 | 24 | 23 | 23 |
  | 4B @ 1.0 | 24 | 22 | 21 |
  | 8B (all 9) | 24 | 24 | 24 |

  4B failures are `names` (requester sign-off not in the notes) plus 2 `changed`. One sample per row per setting, so differences of 1–3 rows are within noise.
- **Cross-cell near-duplicates (masked text, Jaccard ≥ 0.85, pairs):** 4B: 1 at (0.2, 0.5), 0 elsewhere (max 1.00 at (0.2, 0.5)). 8B: 7 / 4 / 4 at T 0.2; 5 / 1 / 0 at T 0.7; 5 / 0 / 1 at T 1.0 (top-p 0.5 / 0.8 / 0.95). Max similarity was 1.00 at top-p 0.5 for all three temperatures: different cells produced identical wording.
- **Echo ("no other club"):** 4B 4–6 rows per setting; 8B 7 rows at every setting. Echo did not change with sampling settings.
- **Timing:**
  - 4B: *measured*, median 4.5 s per ticket (range 3.9–7.2), wall 1,041 s ≈ sum of call latencies (1,035 s).
  - 8B: **not usable as a measurement.** The Mac went into idle sleep at 00:26:59, two minutes after the run started, and the run continued in maintenance wakes. Wall clock was 8,787 s against 4,078 s of summed call time, and per-call medians (11–25 s) are well above the awake 8B trial's 9.6 s. Rerun under `caffeinate -i` before citing any 8B time.

## 2026-10-19 — 8B timing, reproducibility (question 3), declines vs recommended (question 1)

**8B timing, rerun under `caffeinate -i`** (`sweep_qwen3-8b_base_20261019_061836`, `git 7491c47`):
- 24 generated, 24 schema-valid, 24 verified, 0 dead, echo 7. Same counts as the earlier 8B trial.
- *Measured:* median **9.6 s** per ticket (range 8.9–11.6), warm-up 3.7 s, wall 242 s ≈ summed call time 237 s. No sleep during the run.
- This replaces the 8B grid's unusable timing. The 4B (4.5 s per ticket in the grid) is about 2.1× faster.

**Reproducibility (question 3).** Same model digest, seed, settings, and prompt:
- **Immediate rerun:** 3 rows per model at (0.7, 0.8), regenerated straight after the grids. **6 of 6 byte-identical** to the grid file, including 8B rows whose grid run was interrupted by sleep.
- **Across separate runs:** comparing the earlier base-setting trials with the grid at (0.7, 0.8) on all 24 rows: 4B **16 of 24** identical; 8B **21 of 24** (both 8B trials). Every mismatching row had identical seed, `prompt_sha`, `schema_sha`, options, and digest. Differences are small (character similarity 0.91–1.00) and confined to free text (notes, summary, comments), never a form field.
- **Reading:** a fixed seed reproduces most output and often all of it, but it does not guarantee byte-identical tickets between runs on this setup. The cause was not isolated. Likely candidates are numerical non-determinism in GPU inference and Ollama's reuse of cached prompt prefixes between requests; neither is verified. For reproducibility, keep the generated file itself alongside the model digest, seed, settings, and prompt hash. Regenerating cannot be relied on to give the same text.

**Question 1: declines vs recommended,** from both grid files. Declines = `outside_standard` `human_review` rows (**n=6**). Recommended = `venue_dependent` `recommended` rows (**n=4**: the slice has 4 such cells at one row each, not 6).
- **Verified:** declines 6/6 at every setting on both models, except **4B at T 1.0: 5/6 (top-p 0.8) and 4/6 (top-p 0.95)**. Recommended 4/4 at every setting on both models.
- **Echo:** declines 2/6 and recommended 0/4 at every setting on both models. This difference is structural, not about declining. The echo comes from `beyond_template` rows, and recommended rows can never be `beyond_template`.
- **Reading:** with n=6 and n=4 and one sample per row, the only visible signal is the 4B losing declines first at the highest temperature. It is a hint, not a result.

## 2026-10-19 — history rewritten before first push

Before `tc2-axes` was first pushed to the public repo, one line in `use_case/stakeholders.md` and one commit message were reworded across the unpushed history so that a real location and a personnel reference never become public. Every commit after `03994b9` got a new hash. The hashes quoted in this log have been updated.

**Run manifests in `use_case/data/` were written before the rewrite and still record the old hashes:**

| Old (in manifests) | New (in history) | Commit |
|---|---|---|
| `791f524` | `70f17d9` | Remove the deepeval export from generate.py |
| `083213d` | `2718b05` | Add local open-weight sweep (sweep.py) |
| `dc7234f` | `8498faf` | Code-pick employee names for fixed rows |
| `32e81c8` | `7491c47` | Log the qwen3 4B and 8B grids |

The code in each pair is identical; only the hash changed.

## 2026-10-20 — axes revision 6: two jobs per ticket (plan and prompt change)

- **Context correction:** every onboarding ticket carries two jobs: (1) a member record in the club-management system, for every employee, traditionally handled by the hiring manager or People Ops; (2) a staff login with a role, which depends on the role.
- **Renamed scope values:** `login_from_template` → `member_plus_staff_login`; `membership_only` → `member_record_only` (`axes.md`, `DATASHEET.md`, `picks.py`, `generate.py`, `verify.py`).
- **Member record never changed:** "membership" was removed from the changed-detail pool; changes are now start date or club only (18 each). `membership_required` is YES on every generated row, and `expected_proposal.membership_required` is always true.
- **Rule 3 addition:** "the member record follows the ticket and is always created." The login rule is unchanged.
- **New open question Q8:** is member-record creation in scope for the agent, or redirected to People Ops? Impact: all `member_record_only` rows (44 rows, 32 cells).
- **Prompt change:** the generation prompt now states both jobs explicitly, and the comment instruction no longer offers a membership change. **Every `prompt_sha` changes.** All runs before this entry (hosted runs, both qwen3 grids, the fixed-row regeneration, and the 20-ticket review set) used the old wording and the old scope names, and their stored `axes.scope` values use the old names.
- **Plan check:** 126 rows, 36/49/36/5 mix, and Rule 4 balance (3 agree / 3 disagree per scope) all unchanged.
