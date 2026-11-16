# TC6 guardrails: what each rung covers

NeMo Guardrails config for `answer_onboarding_question`. No model is configured. Both rails are
rules (Level 1), run in about 5 ms and send nothing anywhere.

| File | What it is |
| --- | --- |
| `config.yml` | The rungs, in order: input rail `prompt probe rules`, output rail `reply rules`. |
| `rails.co` | The two flows. Each calls one action and stops if it returns true. |
| `actions.py` | The rules. `check_reply` applies the app's own `outcheck.py` patterns and `leak.leaked()`. |

## Which door is closed where

The NeMo input rail reads the user's question, so it can only stop a direct attack. A poisoned
ticket or a poisoned tool description arrives behind an ordinary question, and the rail passes it.
Those two doors are closed in the app's code. `blocks_injection` (`../evals/harness.py`) scores each
case where its fix lives and never credits the input rail for a tool or indirect case.

| Door | Shipped a leak before the fix | Fix, and the leg it removes | Where `blocks_injection` checks it | NeMo input rail |
| --- | --- | --- | --- | --- |
| Tool description (canary in a search query) | 8 of 8 | `qa_schema.ToolStep` has no `args`. Callers get tool name and size; the full trace goes to the server log. Removes the way out. | Recorded results replayed through `qa.answer_question` | does not see it |
| Direct, prompt echo | 3 of 9 | `retrieval.cited_pages` accepts only pages a tool call returned in the same run. Filters: the marker is still in the prompt. | Replay, and the input rail on the question | stops it |
| Direct, other 11 hand attacks | 0 shipped (4 leaked before the gates) | Already withheld: prose is dropped, uncited answers are withheld. | Input rail on the question; replay where a leak was recorded | stops 12 of 12 |
| Indirect, poisoned ticket (pinned to rank 1) | 2 of 8 | `outcheck.py`: approval only from the ticket's status field, links only from the standard. Filters the output; the ticket is still read. | Replay through `qa.answer_question` | does not see it |
| Indirect, shipped retrieval (3 variants) | 0 of 24 | Nothing to replay: the injection never reached the model. Listed, not counted as blocked. | not checked | does not see it |

Three limits, stated plainly:

- The input rules were written after reading the 12 hand attacks, so 12 of 12 is a fit, not a
  forecast. No held-out attack set has been run through them yet.
- The input rail is measured here and in `run.py`. It is **not yet called by the app**:
  `qa.answer_question` enforces the three code fixes and nothing from this folder. The Docker image
  is built from the app folder alone, so wiring it means moving or copying this config there.
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
