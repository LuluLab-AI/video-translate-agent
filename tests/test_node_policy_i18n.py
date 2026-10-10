"""Real bundled Node subprocess against a local HTTP mock; never a paid API."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from video_translate import policy_client as policy
from video_translate.interaction_language import save_language_context, select_interaction_language


@pytest.fixture
def local_policy_server(monkeypatch):
    requests = []
    state = {"status": "Succeeded"}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return
        def respond(self, value):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(("POST", self.path, self.headers.get("Authorization"), body))
            self.respond({"id": "task-1", "status": "Queued"})
        def do_GET(self):
            requests.append(("GET", self.path, self.headers.get("Authorization"), None))
            self.respond({"id": "task-1", "status": state["status"],
                          "output": {"success": True, "action": "cleanup_policy", "policy_version": "fixture-v1"}})
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("LULULAB_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("LULULAB_API_KEY", "fixture-key")
    monkeypatch.delenv("VIDEO_TRANSLATE_POLICY_WORKFLOW_ID", raising=False)
    try:
        assert policy.find_node() is not None, "Node.js 18+ is required for this regression suite"
        yield requests, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_node_submit_fetch_cache_independent_of_interaction_locale(local_policy_server, tmp_path):
    requests, state = local_policy_server
    payload = {"schema_version": 1, "action": "cleanup_policy", "tracks": []}
    cache = tmp_path / "cleanup_policy_result.json"
    context = tmp_path / "interaction_language.json"
    save_language_context(context, select_interaction_language(task_language="pt-BR"))
    first = policy.cached_policy(payload, cache)
    save_language_context(context, select_interaction_language(explicit="ja-JP"))
    assert policy.cached_policy(payload, cache) == first
    assert [r[0] for r in requests] == ["POST", "GET"]
    assert requests[0][1] == "/tasks"
    assert requests[0][2] == "fixture-key"  # Raw auth, never Bearer; key only via stdin.
    assert requests[0][3] == {"workflowId": "VideoTranslatePolicyV1", "input": payload}
    assert requests[1][1] == "/tasks/task-1"
    assert all("interactionLocale" not in json.dumps(r[3]) for r in requests)


def test_node_timeout_resumes_same_task_without_resubmitting(local_policy_server, tmp_path, monkeypatch):
    requests, state = local_policy_server
    state["status"] = "Running"
    clock = iter([0.0, 121.0, 200.0])
    monkeypatch.setattr(policy.time, "monotonic", lambda: next(clock))
    payload = {"action": "cleanup_policy"}
    cache = tmp_path / "cleanup_policy_result.json"
    with pytest.raises(policy.PolicyError, match="POLICY_TIMEOUT"):
        policy.cached_policy(payload, cache)
    state["status"] = "Succeeded"
    assert policy.cached_policy(payload, cache)["success"] is True
    assert [r[0] for r in requests] == ["POST", "GET", "GET"]
    assert {r[1] for r in requests if r[0] == "GET"} == {"/tasks/task-1"}


def test_node_terminal_failure_preserves_saved_task(local_policy_server, tmp_path):
    requests, state = local_policy_server
    state["status"] = "Failed"
    cache = tmp_path / "cleanup_policy_result.json"
    with pytest.raises(policy.PolicyError, match="REMOTE_POLICY_FAILED"):
        policy.cached_policy({"action": "cleanup_policy"}, cache)
    assert json.loads(cache.read_text())["task_id"] == "task-1"
    assert [r[0] for r in requests] == ["POST", "GET"]


def test_api_key_reading_uses_existing_precedence(monkeypatch):
    for name in ("LULULAB_API_KEY", "LINGZHI_API_KEY", "LZSTUDIO_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    calls = []
    monkeypatch.setattr(policy, "read_credential", lambda provider, **kwargs: calls.append(provider) or "fixture-key")
    assert policy._api_key() == "fixture-key"
    assert calls == ["lululab"]
    monkeypatch.setenv("LULULAB_API_KEY", "private-test-key")
    assert policy._api_key() == "private-test-key"
    assert calls == ["lululab"]
