"""Pins local_guard: attack traffic can only reach a measured local model, direct over loopback.

No model calls and no network: the Ollama daemon is faked everywhere, and the tests that build an
HTTP client run with socket connections turned into errors. The probe runs in a fresh interpreter
so the app is imported after the switch, as attack.py does, with a hosted RETRIEVAL_MODEL, proxy
variables and an OLLAMA_API_KEY planted in the environment to prove the guard overrides them.

    uv run --project 01_Product_Engineering/challenge python -m unittest discover -s use_case/evals/tc6
"""

import json
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
APP = ROOT / "01_Product_Engineering/challenge"
sys.path[:0] = [str(HERE)]

import httpcore  # noqa: E402
import httpx  # noqa: E402
import local_guard  # noqa: E402

BASE = "http://localhost:11434"
CHAT = "ollama_chat/qwen2.5:7b"
EMBED = "ollama/nomic-embed-text"
PROXIES = {"HTTP_PROXY": "http://proxy.example.com:8080", "HTTPS_PROXY": "http://proxy.example.com:8080",
           "ALL_PROXY": "http://proxy.example.com:8080", "http_proxy": "http://proxy.example.com:8080"}


def daemon(show=None, models=None, calls=None):
    """A fake Ollama metadata API: a healthy local daemon unless told otherwise."""
    local = [{"name": "qwen2.5:7b", "size": 4_683_087_332, "digest": "845dbda0ea48"},
             {"name": "nomic-embed-text:latest", "size": 274_302_450, "digest": "0a109f422b47"}]

    def fetch(base, path, payload):
        if calls is not None:
            calls.append((base, path, payload))
        if path == "/api/show":
            return {"details": {"format": "gguf"}, "remote_model": None} if show is None else show
        return {"models": local if models is None else models}
    return fetch


def no_network(*args, **kwargs):
    raise AssertionError("a test tried to open a network connection")


class Allowlist(unittest.TestCase):
    def test_measured_models_on_loopback_pass(self):
        for model in (CHAT, EMBED):
            local_guard.require_local(model, BASE)
        local_guard.require_local(CHAT, "http://127.0.0.1:11434")

    def test_models_outside_the_allowlist_are_refused(self):
        for model in ("ollama_chat/gemma4:cloud", "ollama/gemma4:cloud", "ollama_chat/qwen2.5:7b-cloud",
                      "ollama_chat/llama3.2:3b", "openrouter/anthropic/claude-sonnet-5.5", "", None):
            with self.subTest(model=model), self.assertRaises(SystemExit) as raised:
                local_guard.require_local(model, BASE)
            self.assertIn("REFUSING", str(raised.exception))

    def test_a_cloud_name_is_refused_even_if_someone_allowlists_it(self):
        with mock.patch.object(local_guard, "ALLOWED_MODELS", frozenset({"ollama_chat/gemma4:cloud"})):
            with self.assertRaises(SystemExit) as raised:
                local_guard.require_local("ollama_chat/gemma4:cloud", BASE)
        self.assertIn("remote", str(raised.exception))

    def test_non_loopback_base_is_refused(self):
        for base in ("https://ollama.com", "http://proxy.example.com:11434", "http://localhost.example.com:11434", "", None):
            with self.subTest(base=base), self.assertRaises(SystemExit):
                local_guard.require_local(CHAT, base)


class DaemonCheck(unittest.TestCase):
    def refused(self, fetch, model=CHAT):
        with self.assertRaises(SystemExit) as raised:
            local_guard.require_local_weights(model, BASE, fetch)
        self.assertIn("REFUSING", str(raised.exception))
        return str(raised.exception)

    def test_local_model_with_weights_on_disk_passes(self):
        calls = []
        local_guard.require_local_weights(CHAT, BASE, daemon(calls=calls))
        local_guard.require_local_weights(EMBED, BASE, daemon(calls=calls))
        self.assertEqual(calls[0], (BASE, "/api/show", {"model": "qwen2.5:7b"}))

    def test_remote_metadata_in_show_is_refused(self):
        for show in ({"details": {"format": "gguf"}, "remote_model": "qwen2.5:7b"},
                     {"details": {"format": "gguf"}, "remote_host": "https://ollama.com:443"}):
            with self.subTest(show=show):
                self.assertIn("remote", self.refused(daemon(show=show)))

    def test_remote_metadata_in_the_model_list_is_refused(self):
        models = [{"name": "qwen2.5:7b", "size": 4_683_087_332, "digest": "d", "remote_host": "https://ollama.com:443"}]
        self.assertIn("remote", self.refused(daemon(models=models)))

    def test_stub_sized_model_is_refused(self):
        self.assertIn("no weights on disk", self.refused(daemon(models=[{"name": "qwen2.5:7b", "size": 382, "digest": "d"}])))

    def test_model_without_digest_or_format_is_refused(self):
        self.refused(daemon(models=[{"name": "qwen2.5:7b", "size": 4_683_087_332}]))
        self.refused(daemon(show={"details": {}}))

    def test_model_the_daemon_does_not_list_is_refused(self):
        self.assertIn("does not list", self.refused(daemon(models=[])))

    def test_unknown_answer_is_refused(self):
        def down(base, path, payload):
            raise OSError("connection refused")
        self.assertIn("unknown", self.refused(down))
        self.assertIn("unknown", self.refused(lambda base, path, payload: ["not", "an", "object"]))
        self.assertIn("unknown", self.refused(lambda base, path, payload: {"models": "garbage"} if path == "/api/tags" else {}))

    def test_model_off_the_allowlist_is_refused_before_the_daemon_is_asked(self):
        calls = []
        self.refused(daemon(calls=calls), model="ollama_chat/gemma4:cloud")
        self.assertEqual(calls, [])

    def test_the_real_metadata_call_uses_no_proxy_and_refuses_redirects(self):
        seen = {}

        def build_opener(*handlers):
            seen["handlers"] = handlers
            raise OSError("stop before any connection")
        with mock.patch.object(local_guard.urllib.request, "build_opener", build_opener), self.assertRaises(OSError):
            local_guard._ollama_json(BASE, "/api/tags", None)
        proxy = [h for h in seen["handlers"] if isinstance(h, local_guard.urllib.request.ProxyHandler)]
        self.assertEqual(proxy[0].proxies, {})
        self.assertIn(local_guard._NoRedirect, seen["handlers"])
        with self.assertRaises(SystemExit):
            local_guard._NoRedirect().redirect_request(mock.Mock(full_url=BASE), None, 302, "Found", {}, "http://proxy.example.com/")


class Redirecting:
    """A connection pool that never touches the network: answers every request with a redirect."""

    def __init__(self):
        self.hosts = []

    def handle_request(self, request):
        self.hosts.append(request.url.host.decode())
        return httpcore.Response(302, headers=[(b"location", b"http://proxy.example.com/api/chat")], content=b"")

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


@mock.patch.object(socket.socket, "connect", no_network)
@mock.patch.object(socket, "getaddrinfo", no_network)
class Transport(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, PROXIES)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("NO_PROXY", None)
        os.environ.pop("no_proxy", None)
        lock = mock.patch.multiple(httpx.HTTPTransport, handle_request=httpx.HTTPTransport.handle_request)
        lock.start()
        self.addCleanup(lock.stop)
        alock = mock.patch.multiple(httpx.AsyncHTTPTransport, handle_async_request=httpx.AsyncHTTPTransport.handle_async_request)
        alock.start()
        self.addCleanup(alock.stop)

    def pool(self, url):
        with httpx.Client() as client:
            return client._transport_for_url(httpx.URL(url))._pool

    def test_inherited_proxy_would_be_selected_without_the_guard(self):
        # The hole the review found: this is what the guard has to undo.
        self.assertIsInstance(self.pool(f"{BASE}/api/chat"), httpcore.HTTPProxy)
        with self.assertRaises(SystemExit):
            local_guard.assert_direct_transport([f"{BASE}/api/chat"])

    def test_guard_forces_direct_transport_for_chat_and_embeddings(self):
        local_guard.force_direct_loopback()
        for path in ("/api/chat", "/api/embed", "/api/generate"):
            for base in (BASE, "http://127.0.0.1:11434"):
                with self.subTest(url=base + path):
                    self.assertNotIsInstance(self.pool(base + path), (httpcore.HTTPProxy, httpcore.SOCKSProxy))
        local_guard.assert_direct_transport([f"{BASE}/api/chat", f"{BASE}/api/embed"])
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            self.assertEqual(os.environ[name], "")

    def test_lock_refuses_a_proxied_request_to_loopback(self):
        local_guard.install_loopback_lock()
        with httpx.Client(proxy="http://proxy.example.com:8080", trust_env=False) as client:
            with self.assertRaises(SystemExit) as raised:
                client.post(f"{BASE}/api/chat", json={})
        self.assertIn("proxy", str(raised.exception))

    def test_lock_refuses_a_request_off_loopback(self):
        local_guard.install_loopback_lock()
        with httpx.Client(trust_env=False) as client, self.assertRaises(SystemExit) as raised:
            client.post("https://api.example.com/v1/chat/completions", json={})
        self.assertIn("leave this machine", str(raised.exception))

    def test_lock_refuses_a_redirect_off_loopback(self):
        local_guard.install_loopback_lock()
        transport, pool = httpx.HTTPTransport(), Redirecting()
        transport._pool = pool
        with httpx.Client(transport=transport, follow_redirects=True, trust_env=False) as client:
            with self.assertRaises(SystemExit) as raised:
                client.post(f"{BASE}/api/chat", json={})
        self.assertIn("leave this machine", str(raised.exception))
        self.assertEqual(pool.hosts, ["localhost"])  # the second hop never reached a connection pool


PROBE = f"""
import json, os, socket, sys
def no_network(*a, **k):
    raise AssertionError("the probe tried to open a network connection")
socket.socket.connect = no_network
socket.getaddrinfo = no_network
sys.path[:0] = [{str(HERE)!r}, {str(APP)!r}]
import local_guard
import test_local_guard
show = json.loads(os.environ.get("FAKE_SHOW") or "null")
local_guard.switch_app_to_injection_model(test_local_guard.daemon(show=show))
import retrieval
local_guard.assert_app_is_local()
import httpx
from litellm.llms.custom_httpx.http_handler import _get_httpx_client
client = _get_httpx_client().client
pool = client._transport_for_url(httpx.URL("http://localhost:11434/api/chat"))._pool
try:
    client.post("https://api.example.com/v1/chat/completions", json={{}})
    off_machine = "sent"
except SystemExit as exc:
    off_machine = str(exc)
print(json.dumps({{"chat": retrieval.CHAT_MODEL, "kwargs": retrieval.CHAT_KWARGS, "embed": retrieval.EMBED_MODEL,
                  "retrieval_model_env": os.environ.get("RETRIEVAL_MODEL"), "litellm_pool": type(pool).__name__,
                  "off_machine": off_machine,
                  "env": {{k: os.environ.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "NO_PROXY", "OLLAMA_API_KEY")}}}}))
"""


class ResolvedChatModel(unittest.TestCase):
    def probe(self, **env):
        return subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True, cwd=ROOT,
                              env=os.environ | {"INJECTION_MODEL": CHAT, "INJECTION_API_BASE": BASE} | env)

    def test_chat_model_resolves_to_ollama_even_with_hosted_retrieval_model(self):
        out = self.probe(RETRIEVAL_MODEL="openrouter/anthropic/claude-sonnet-5.5")
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        resolved = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(resolved["chat"], CHAT)
        # Set explicitly, not blanked: nothing downstream can fall back to a hosted default.
        self.assertEqual(resolved["retrieval_model_env"], CHAT)
        self.assertNotIn("extra_headers", resolved["kwargs"])
        self.assertEqual(resolved["embed"], EMBED)

    def test_litellm_client_goes_direct_despite_inherited_proxies_and_ollama_key(self):
        out = self.probe(OLLAMA_API_KEY="synthetic-not-a-key", **PROXIES)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        resolved = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(resolved["litellm_pool"], "ConnectionPool")  # not HTTPProxy
        self.assertIn("leave this machine", resolved["off_machine"])
        self.assertEqual(resolved["env"], {"HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "", "http_proxy": "",
                                           "NO_PROXY": "localhost,127.0.0.1,::1", "OLLAMA_API_KEY": ""})

    def test_hosted_injection_model_is_refused(self):
        out = self.probe(INJECTION_MODEL="openrouter/anthropic/claude-sonnet-5.5")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("REFUSING", out.stderr)

    def test_cloud_model_on_loopback_is_refused(self):
        out = self.probe(INJECTION_MODEL="ollama_chat/gemma4:cloud")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("REFUSING", out.stderr)
        self.assertNotIn("retrieval", out.stdout)

    def test_allowlisted_name_the_daemon_marks_remote_is_refused_before_the_app_loads(self):
        out = self.probe(FAKE_SHOW=json.dumps({"details": {"format": "gguf"}, "remote_host": "https://ollama.com:443"}))
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("marks 'ollama_chat/qwen2.5:7b' as a remote model", out.stderr)


if __name__ == "__main__":
    unittest.main()
