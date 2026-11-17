"""Refuse to send attack text anywhere but a local model. Imported before the app is.

TC6 Steps 2-3 send injection-shaped prompts. Those go only to the INJECTION_* endpoint
(Ollama on this machine), never to a hosted provider. This module switches the APP's own
model config to that endpoint through the environment (the same LLM_MODEL / LLM_API_BASE /
EMBED_* variables the shipped app reads), then asserts after import that the app really
resolved to it. Any doubt is a hard stop, not a warning.

A loopback URL is not enough on its own, for two reasons, and each has its own check:

1. Ollama can serve cloud models through the local API with the daemon's signed-in account, so
   `ollama_chat/<anything>` on localhost may still be hosted inference. Only the models named in
   ALLOWED_MODELS pass (the ones the committed runs measured), a name that looks remote is
   refused, and the daemon is asked, before any attack text is loaded, whether each model is a
   local one with weights on disk (require_local_weights). No answer is a refusal.
2. An inherited HTTP(S)_PROXY / ALL_PROXY would carry a request for localhost to the proxy. The
   proxy variables are blanked and NO_PROXY set for loopback (force_direct_loopback), and every
   httpx transport in the process then refuses a request that is not direct to loopback, which
   also stops a redirect that points off this machine (install_loopback_lock).
"""

import json
import os
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCAL_EMBED = "ollama/nomic-embed-text"
# The models the committed runs in runs/*.jsonl were measured on, plus the local embedder. To
# attack another local model, add it here on purpose; nothing in the environment can widen this.
ALLOWED_MODELS = frozenset({"ollama_chat/qwen2.5:7b", LOCAL_EMBED})
# Ollama names its hosted models with a cloud tag (":cloud", "-cloud"); never valid here.
REMOTE_NAME_MARKS = ("cloud", "remote")
# A cloud model is a stub of a few hundred bytes in the local store; real weights are far larger
# (the smallest model allowed here, the embedder, is about 274 MB).
MIN_WEIGHT_BYTES = 50_000_000
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY")
NO_PROXY = "localhost,127.0.0.1,::1"
# Blank, not popped: litellm calls load_dotenv() on import, which would put a popped variable
# straight back from .env (seen: EMBED_API_KEY). The app and the HTTP clients treat "" as unset.
BLANKED = ("LLM_EXTRA_HEADERS", "EMBED_API_KEY", "OLLAMA_API_KEY")


def refuse(why: str):
    raise SystemExit(f"REFUSING: attack traffic must go to a local Ollama model; {why}")


def require_local(model: str | None, base: str | None) -> None:
    """SystemExit unless `model` is on the allowlist, not named as remote, and `base` is loopback."""
    host = urlparse(base or "").hostname
    if not model or model not in ALLOWED_MODELS:
        refuse(f"model={model!r} is not one of the measured local models {sorted(ALLOWED_MODELS)}")
    if any(mark in model.lower() for mark in REMOTE_NAME_MARKS):
        refuse(f"model={model!r} is named as a remote model")
    if host not in LOCAL_HOSTS:
        refuse(f"base={base!r} is not a loopback URL")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        refuse(f"the Ollama daemon answered {req.full_url} with a redirect to {newurl!r}")


def _ollama_json(base: str, path: str, payload: dict | None):
    """One metadata call to the local daemon: no proxy (not even the system one), no redirects."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=10) as response:
        return json.loads(response.read().decode())


def _remote_fields(record: dict) -> dict:
    return {key: value for key, value in record.items() if key.startswith("remote") and value}


def require_local_weights(model: str, base: str, fetch=_ollama_json) -> None:
    """SystemExit unless the daemon at `base` says `model` is a local model with weights on disk.

    Asks /api/show and /api/tags. Refused: a model with remote_model / remote_host metadata (how
    Ollama marks a cloud model), a model the daemon does not list, a listed model without a digest
    or with a stub-sized blob, and any answer that cannot be read. `fetch` is faked in the tests.
    """
    require_local(model, base)
    name = model.split("/", 1)[1]
    try:
        show = fetch(base, "/api/show", {"model": name})
        tags = fetch(base, "/api/tags", None)
        if not isinstance(show, dict) or not isinstance(tags, dict):
            raise TypeError("not a JSON object")
        if not isinstance(tags.get("models"), list):
            raise TypeError("no model list")
        listed = [m for m in tags["models"] if isinstance(m, dict) and m.get("name") in (name, f"{name}:latest")]
    except SystemExit:
        raise
    except Exception as exc:
        refuse(f"could not confirm {model!r} is local, the daemon's answer is unknown ({type(exc).__name__}: {exc})")
    if _remote_fields(show) or any(_remote_fields(m) for m in listed):
        refuse(f"the daemon marks {model!r} as a remote model: {_remote_fields(show) or [_remote_fields(m) for m in listed]}")
    if len(listed) != 1:
        refuse(f"the daemon does not list exactly one local copy of {model!r} (found {len(listed)})")
    size, digest = listed[0].get("size"), listed[0].get("digest")
    if not digest or not isinstance(size, int) or size < MIN_WEIGHT_BYTES:
        refuse(f"{model!r} has no weights on disk according to the daemon (size={size!r}, digest={digest!r})")
    if not (show.get("details") or {}).get("format"):
        refuse(f"the daemon reports no weight format for {model!r}")


def force_direct_loopback() -> None:
    """Blank every proxy variable and exempt loopback, before any HTTP client is built.

    NO_PROXY is set as well as the blanking: with it present, urllib (which httpx asks) stops at
    the environment and never falls through to the macOS system proxy settings.
    """
    for name in PROXY_VARS:
        os.environ[name] = os.environ[name.lower()] = ""
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = NO_PROXY


def _check_direct_loopback(transport, request) -> None:
    import httpcore

    if request.url.host not in LOCAL_HOSTS:
        refuse(f"an HTTP request was about to leave this machine: {request.url.scheme}://{request.url.host}")
    if isinstance(getattr(transport, "_pool", None), (httpcore.HTTPProxy, httpcore.SOCKSProxy, httpcore.AsyncHTTPProxy, httpcore.AsyncSOCKSProxy)):
        refuse(f"a proxy was selected for {request.url.scheme}://{request.url.host}")


def install_loopback_lock() -> None:
    """Every httpx transport in this process refuses a request that is not direct to loopback.

    litellm sends chat and embeddings through httpx; some of its clients follow redirects. Each
    hop, a redirect included, passes through the transport, so this stops both a proxied request
    and a redirect off the machine at the last point before a socket is opened. Idempotent.
    """
    import httpx

    if getattr(httpx.HTTPTransport.handle_request, "_loopback_lock", False):
        return
    sync_send, async_send = httpx.HTTPTransport.handle_request, httpx.AsyncHTTPTransport.handle_async_request

    def handle_request(self, request):
        _check_direct_loopback(self, request)
        return sync_send(self, request)

    async def handle_async_request(self, request):
        _check_direct_loopback(self, request)
        return await async_send(self, request)

    handle_request._loopback_lock = True
    httpx.HTTPTransport.handle_request = handle_request
    httpx.AsyncHTTPTransport.handle_async_request = handle_async_request


def switch_app_to_injection_model(fetch=_ollama_json) -> tuple[str, str]:
    """Point the app's env-driven model config at INJECTION_MODEL / INJECTION_API_BASE. Call before importing the app."""
    from dotenv import dotenv_values

    if any(name in sys.modules for name in ("llm", "retrieval", "qa", "app")):
        raise SystemExit("REFUSING: the app was imported before its model config was switched to the local model")
    values = dotenv_values(ROOT / ".env")
    model = os.environ.get("INJECTION_MODEL") or values.get("INJECTION_MODEL")
    base = os.environ.get("INJECTION_API_BASE") or values.get("INJECTION_API_BASE")
    require_local(model, base)
    force_direct_loopback()
    install_loopback_lock()
    # The daemon is asked before the caller loads any attack text (attack.py calls this first).
    require_local_weights(model, base, fetch)
    require_local_weights(LOCAL_EMBED, base, fetch)
    # RETRIEVAL_MODEL is set to the local model, not blanked: retrieval.CHAT_MODEL reads it first,
    # so a hosted RETRIEVAL_MODEL left in .env can never win. With it set, the app drops its own
    # api_base for chat, and litellm routes ollama_chat/* via OLLAMA_API_BASE (set to loopback here).
    os.environ.update({"LLM_MODEL": model, "RETRIEVAL_MODEL": model, "LLM_API_BASE": base,
                       "OLLAMA_API_BASE": base, "EMBED_MODEL": LOCAL_EMBED, "EMBED_API_BASE": base,
                       # litellm fetches a price list from the internet on import unless told not to.
                       "LITELLM_LOCAL_MODEL_COST_MAP": "True"})
    for name in BLANKED:
        os.environ[name] = ""
    return model, base


def assert_direct_transport(urls) -> None:
    """A default httpx client (what litellm builds) would open `urls` directly, not through a proxy."""
    import httpcore
    import httpx

    with httpx.Client() as client:
        for url in urls:
            pool = getattr(client._transport_for_url(httpx.URL(url)), "_pool", None)
            if not isinstance(pool, httpcore.ConnectionPool) or isinstance(pool, (httpcore.HTTPProxy, httpcore.SOCKSProxy)):
                refuse(f"a proxy would be selected for {url!r}")


def assert_app_is_local() -> None:
    """After import: every route the app will use (chat and embeddings) resolves to loopback Ollama, sent direct."""
    import llm
    import retrieval

    # With RETRIEVAL_MODEL set the app passes no api_base for chat; litellm then uses OLLAMA_API_BASE.
    chat_base = retrieval.CHAT_KWARGS.get("api_base") or os.environ.get("OLLAMA_API_BASE")
    embed_base = retrieval.EMBED_KWARGS.get("api_base")
    require_local(retrieval.CHAT_MODEL, chat_base)
    require_local(llm.MODEL, llm.API_BASE)
    require_local(retrieval.EMBED_MODEL, embed_base)
    if "extra_headers" in retrieval.CHAT_KWARGS or "api_key" in retrieval.EMBED_KWARGS:
        raise SystemExit("REFUSING: gateway headers or a provider key survived the switch")
    # litellm's import ran load_dotenv(): a proxy or OLLAMA_API_KEY in .env cannot have come back
    # (the variables were blanked, not popped), but check rather than trust that.
    if any(os.environ.get(name) or os.environ.get(name.lower()) for name in PROXY_VARS) or os.environ.get("OLLAMA_API_KEY"):
        raise SystemExit("REFUSING: a proxy variable or OLLAMA_API_KEY is set after the switch")
    install_loopback_lock()
    assert_direct_transport([f"{chat_base}/api/chat", f"{embed_base}/api/embed"])
