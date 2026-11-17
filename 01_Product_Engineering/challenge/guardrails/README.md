# TC6 guardrails: what each rung covers

NeMo Guardrails config for `answer_onboarding_question`. No model is configured. Both rails are
rules (Level 1), run in about 5 ms and send nothing anywhere.

| File | What it is |
| --- | --- |
| `config.yml` | The rungs, in order: input rail `prompt probe rules`, output rail `reply rules`. |
| `rails.co` | The two flows. Each calls one action and stops if it returns true. |
| `actions.py` | The rules. `check_reply` applies the app's own `outcheck.py` rules: marker, approval, link. |

## Which door is closed where

The NeMo input rail reads the user's question, so it can only stop a direct attack. A poisoned
ticket or a poisoned tool description arrives behind an ordinary question, and the rail passes it.
Those two doors are closed in the app's code. `blocks_injection` (`../../../use_case/evals/harness.py`) scores each
case where its fix lives and never credits the input rail for a tool or indirect case.

| Door | Shipped a leak before the fix | Fix, and the leg it removes | Where `blocks_injection` checks it | NeMo input rail |
| --- | --- | --- | --- | --- |
| Tool description (canary in a search query) | 8 of 8 | `qa_schema.ToolStep` has no `args`. Callers get tool name and size; the full trace goes to the server log. Removes the way out. | Recorded results replayed through `qa.answer_question` | does not see it |
| Direct, prompt echo | 3 of 9 | `retrieval.cited_pages` accepts only pages a tool call returned in the same run. Filters: the marker is still in the prompt. | Replay, and the input rail on the question | stops it |
| Direct, other 11 hand attacks | 0 shipped (4 leaked before the gates) | Already withheld: prose is dropped, uncited answers are withheld. | Input rail on the question; replay where a leak was recorded | stops 12 of 12 |
| Indirect, poisoned ticket (pinned to rank 1) | 2 of 8 | `outcheck.py`: approval only from the ticket's status field, links only from the standard. Filters the output; the ticket is still read. | Replay through `qa.answer_question` | does not see it |
| Indirect, shipped retrieval (3 variants) | 0 of 24 | Nothing to replay: the injection never reached the model. Listed, not counted as blocked. | not checked | does not see it |

Limits, stated plainly:

- The input rules were written after reading the 12 hand attacks, so 12 of 12 is a fit, not a
  forecast. No held-out attack set has been run through them yet.
- The input rail is on the request path: `qa.answer_question` calls `inputrail.stopped_by()` before
  the model, and a stopped question is declined with a fixed reason and `trace.stopped` set to
  `input_rail`. No model or retrieval call is made for it. If the rails cannot be built or run, the
  question is declined too. There is no setting that turns the rail off; tests and measurement
  scripts skip a gate by passing `skip_gates` (see `qa.TC6_GATES`). The output rail is measured by
  `ladder_pass.py` only: on the request path the same rules run in `outcheck.py`, which can also
  read the cited tickets' status fields.
- The input rules match wording. As first written they refused 12 of 24 held-out legitimate
  questions ("system configuration", "admin mode", "internal rules", "your instructions for a
  re-hire"). They were narrowed on 2026-11-16 and now refuse 0 of the 24 and still stop the 12
  direct attacks. The 24 were written by the author of the rules, after reading them, and the
  narrowing was fitted to them, so 0 of 24 is a fit too. What the narrowing gave up: a question
  that says "admin override", "audit mode" or "tell me your instructions" without naming the prompt
  or the marker now reaches the model. Both run files and the list are in
  `use_case/evals/tc6/README.md`.
- The output rail's marker check is `outcheck.carries_marker` (any case, spacing, reversed). It does
  not decode base64; the evals' `leak.leaked()` does, and scores the saved runs.
- The replay tells the citation gate the worst case for it: a recorded run that made a tool call is
  assumed to have retrieved every page it cites. The three prompt echoes that shipped made no tool
  call, so for them the result is certain.

## Level 3, the judge rung: declined

`self check input` and `self check output` are not configured. Reasons:

1. Attack text may not go to a hosted model, so the judge would have to be the local
   `ollama_chat/qwen2.5:7b`. One call to it took 4 to 8 seconds in the saved attack runs, on a
   question that already takes that long. A judge on input and output would roughly triple latency.
2. The three doors that shipped a leak are closed by code that needs no model, and the recorded
   leaks replay clean. A judge has no measured leak left to catch on this attack set.
3. A 7B judge's false-refusal rate on real questions is unmeasured. We did not run it, so there is
   no number here, and the rung is not claimed.

What we accept instead: a novel attack that the rules and the code checks both miss is not caught
at request time. If the judge is wanted later, run it on a sample of saved replies after the fact
and turn what it finds into a rule.
