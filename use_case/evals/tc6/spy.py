"""Record what the model wrote on every turn, before the app drops any of it. Observes only.

retrieval's own result is not enough for "what did the model say": a prose reply comes back as
answer "" (final_step / repair_step / _final), a decline reason is cut at 300 characters, and an
answer made beside a decline is discarded. The spy wraps retrieval.chat_turn, the one function
every model call in run_agent, answer_once and repair_step goes through, and returns each response
unchanged.
"""

import json


def raw_turn(message) -> dict:
    """One model turn as plain data: its prose and each tool call's arguments, uncut."""
    calls = []
    for call in getattr(message, "tool_calls", None) or []:
        args = call.function.arguments
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                pass  # junk arguments are still model text: keep the raw string
        calls.append({"name": call.function.name, "args": args})
    return {"content": getattr(message, "content", None), "tool_calls": calls}


def spy_on_turns(retrieval, turns: list) -> None:
    """Wrap `retrieval.chat_turn` so every model reply is appended to `turns`."""
    real = retrieval.chat_turn

    def chat_turn(*args, **kwargs):
        response = real(*args, **kwargs)
        turns.append(raw_turn(response.choices[0].message))
        return response

    retrieval.chat_turn = chat_turn
