"""TC6 Docker check: one question through qa.answer_question inside the container, with a spy on the model call.

    python /check/docker_check.py "QUESTION"

Prints the model the container is pointed at, whether the reply was declined and by what, and how
many model calls were made. For an attack, run the container with the local model only and no
env file, so no hosted key is present (see README.md, "Docker").
"""
import json
import os
import sys
from unittest.mock import patch
import litellm
import qa
import retrieval
import inputrail
from qa_schema import QuestionRequest
print("model", retrieval.CHAT_MODEL, "| api_base", os.getenv("LLM_API_BASE"), "| hosted keys in env:",
      sorted(k for k in os.environ if k.endswith("_API_KEY")))
real, calls = litellm.completion, []
def spy(*a, **k):
    calls.append(k.get("model"))
    return real(*a, **k)
with patch.object(litellm, "completion", spy):
    out = qa.answer_question(QuestionRequest(question=sys.argv[1]))
print(json.dumps({"declined": out.declined, "decline_reason": out.decline_reason, "stopped": out.trace.stopped,
                  "steps": len(out.trace.steps), "model_calls": len(calls), "rung": inputrail.stopped_by(sys.argv[1])}, indent=1))
