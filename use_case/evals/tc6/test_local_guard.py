"""Pins local_guard: after the switch, the app's resolved chat model is local Ollama. No model calls.

Runs in a fresh interpreter so the app is imported after the switch, as attack.py does, with a
hosted RETRIEVAL_MODEL planted in the environment to prove the guard overrides it.

    uv run --project 01_Product_Engineering/challenge python -m unittest discover -s use_case/evals/tc6
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
APP = ROOT / "01_Product_Engineering/challenge"

PROBE = f"""
import json, os, sys
sys.path[:0] = [{str(HERE)!r}, {str(APP)!r}]
import local_guard
local_guard.switch_app_to_injection_model()
import retrieval
local_guard.assert_app_is_local()
print(json.dumps({{"chat": retrieval.CHAT_MODEL, "kwargs": retrieval.CHAT_KWARGS, "embed": retrieval.EMBED_MODEL,
                  "retrieval_model_env": os.environ.get("RETRIEVAL_MODEL")}}))
"""


class ResolvedChatModel(unittest.TestCase):
    def probe(self, **env):
        out = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True, cwd=ROOT,
                             env=os.environ | {"INJECTION_MODEL": "ollama_chat/qwen2.5:7b",
                                               "INJECTION_API_BASE": "http://localhost:11434"} | env)
        return out

    def test_chat_model_resolves_to_ollama_even_with_hosted_retrieval_model(self):
        out = self.probe(RETRIEVAL_MODEL="openrouter/anthropic/claude-sonnet-5.5")
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        resolved = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(resolved["chat"], "ollama_chat/qwen2.5:7b")
        # Set explicitly, not blanked: nothing downstream can fall back to a hosted default.
        self.assertEqual(resolved["retrieval_model_env"], "ollama_chat/qwen2.5:7b")
        self.assertTrue(resolved["chat"].startswith(("ollama/", "ollama_chat/")))
        self.assertNotIn("extra_headers", resolved["kwargs"])
        self.assertEqual(resolved["embed"], "ollama/nomic-embed-text")

    def test_hosted_injection_model_is_refused(self):
        out = self.probe(INJECTION_MODEL="openrouter/anthropic/claude-sonnet-5.5")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("REFUSING", out.stderr)


if __name__ == "__main__":
    unittest.main()
