"""Refuse to send attack text anywhere but a local model. Imported before the app is.

TC6 Steps 2-3 send injection-shaped prompts. Those go only to the INJECTION_* endpoint
(Ollama on this machine), never to a hosted provider. This module switches the APP's own
model config to that endpoint through the environment (the same LLM_MODEL / LLM_API_BASE /
EMBED_* variables the shipped app reads), then asserts after import that the app really
resolved to it. Any doubt is a hard stop, not a warning.
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCAL_PREFIXES = ("ollama/", "ollama_chat/")
LOCAL_EMBED = "ollama/nomic-embed-text"


def require_local(model: str | None, base: str | None) -> None:
    """SystemExit unless `model` is an Ollama model and `base` is a loopback URL."""
    host = urlparse(base or "").hostname
    if not model or not model.startswith(LOCAL_PREFIXES) or host not in LOCAL_HOSTS:
        raise SystemExit(f"REFUSING: attack traffic must go to a local Ollama model; got model={model!r} base={base!r}")


def switch_app_to_injection_model() -> tuple[str, str]:
    """Point the app's env-driven model config at INJECTION_MODEL / INJECTION_API_BASE. Call before importing the app."""
    from dotenv import dotenv_values

    if any(name in sys.modules for name in ("llm", "retrieval", "qa", "app")):
        raise SystemExit("REFUSING: the app was imported before its model config was switched to the local model")
    values = dotenv_values(ROOT / ".env")
    model = os.environ.get("INJECTION_MODEL") or values.get("INJECTION_MODEL")
    base = os.environ.get("INJECTION_API_BASE") or values.get("INJECTION_API_BASE")
    require_local(model, base)
    os.environ.update({"LLM_MODEL": model, "LLM_API_BASE": base, "OLLAMA_API_BASE": base,
                       "EMBED_MODEL": LOCAL_EMBED, "EMBED_API_BASE": base})
    # Blank, not popped: litellm calls load_dotenv() on import, which would put a popped
    # provider key straight back from .env (seen: EMBED_API_KEY). The app treats "" as unset.
    for name in ("RETRIEVAL_MODEL", "LLM_EXTRA_HEADERS", "EMBED_API_KEY"):
        os.environ[name] = ""
    return model, base


def assert_app_is_local() -> None:
    """After import: every route the app will use (chat and embeddings) resolves to loopback Ollama."""
    import llm
    import retrieval

    require_local(retrieval.CHAT_MODEL, retrieval.CHAT_KWARGS.get("api_base"))
    require_local(llm.MODEL, llm.API_BASE)
    require_local(retrieval.EMBED_MODEL, retrieval.EMBED_KWARGS.get("api_base"))
    if "extra_headers" in retrieval.CHAT_KWARGS or "api_key" in retrieval.EMBED_KWARGS:
        raise SystemExit("REFUSING: gateway headers or a provider key survived the switch")
