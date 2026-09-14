"""Tests for the FastAPI web layer, driven through a fake service so no
network, HikerAPI token, or Ollama is needed."""
import time
import types

import pytest
from fastapi.testclient import TestClient

import src.web.app as appmod
import src.web.history as history


@pytest.fixture
def client(tmp_path, monkeypatch):
    history.targets.path = tmp_path / "targets.json"
    history.queries.path = tmp_path / "queries.json"

    class FakeApi:
        cache_store = cache_ttl_seconds = max_calls = on_call = None

    def fake_build(target):
        if target == "nobody":
            raise appmod.TargetNotFoundError("@nobody not found")
        return types.SimpleNamespace(
            api=FakeApi(), target=target, target_id=1 if target else None, backend_name="fake",
            api_call_count=0,
            user={"username": target.lstrip("@").lower()} if target else {},
            get_user_info=lambda **k: {"follower_count": 10},
            get_media_type=lambda **k: {"photos": 1, "previews": [{"id": "x", "media_url": "u"}]},
            search_hashtag=lambda **k: {"hashtag": "#milano", "posts": 0, "authors": [], "previews": []},
            search_location=lambda **k: {"place": None, "posts": 0, "authors": [], "previews": []},
        )

    monkeypatch.setattr(appmod, "build_service", fake_build)
    monkeypatch.setattr(appmod.ollama, "chat", lambda **kw: types.SimpleNamespace(
        message=types.SimpleNamespace(content="fatto", tool_calls=None)))
    return TestClient(appmod.app)


def test_tools_endpoint_lists_commands(client):
    specs = client.get("/api/tools").json()
    names = {s["name"] for s in specs}
    assert {"get_user_info", "get_media_type", "compare_with", "get_highlights"} <= names
    compare = next(s for s in specs if s["name"] == "compare_with")
    assert {p["name"] for p in compare["params"]} == {"other_username", "scope", "limit"}
    scope = next(p for p in compare["params"] if p["name"] == "scope")
    assert scope["choices"] == ["both", "followers", "followings"]  # rendered as a dropdown in Base mode


def test_run_executes_selected_commands_in_order(client):
    r = client.post("/api/run", json={"target": "alice", "calls": [
        {"name": "get_user_info"}, {"name": "get_media_type"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == ""  # base mode has no model answer
    assert [c["name"] for c in body["tool_calls"]] == ["get_user_info", "get_media_type"]


def test_search_commands_run_without_a_target(client, monkeypatch):
    """Hashtag/place searches belong to no account: no username must be
    resolved (that would cost a request for nothing)."""
    built = []

    def fake_build(target):
        built.append(target)
        class FakeApi:
            cache_store = cache_ttl_seconds = max_calls = on_call = cancelled = None
        return types.SimpleNamespace(
            api=FakeApi(), target=target, target_id=None, backend_name="fake", api_call_count=0, user={},
            search_hashtag=lambda **k: {"hashtag": "#milano", "posts": 0, "authors": [], "previews": []})

    monkeypatch.setattr(appmod, "build_service", fake_build)
    r = client.post("/api/run", json={"calls": [{"name": "search_hashtag", "args": {"hashtag": "milano"}}]})
    assert r.status_code == 200
    assert built == [None]  # no target was resolved
    assert client.get("/api/history/targets").json() == []  # and none recorded


def test_target_still_required_for_target_commands(client):
    r = client.post("/api/run", json={"calls": [{"name": "get_user_info"}]})
    assert r.status_code == 400
    assert "get_user_info" in r.json()["detail"]


def test_ai_mode_runs_without_a_target_on_the_search_tools(client, monkeypatch):
    """No target means the hashtag/place searches only - but the agent still
    runs, instead of being refused before it starts."""
    offered = {}

    def fake_chat(**kw):
        offered["tools"] = [fn.__name__ for fn in kw["tools"]]
        offered["system"] = kw["messages"][0]["content"]
        return types.SimpleNamespace(message=types.SimpleNamespace(content="ecco", tool_calls=None))

    monkeypatch.setattr(appmod.ollama, "chat", fake_chat)
    r = client.post("/api/query", json={"message": "post con #milano"})
    assert r.status_code == 200 and r.json()["answer"] == "ecco"
    assert set(offered["tools"]) == {"search_hashtag", "search_location"}
    assert "No target account is set" in offered["system"]
    assert client.get("/api/history/targets").json() == []  # nothing to record


def test_ai_mode_still_needs_a_message(client):
    assert client.post("/api/query", json={"target": "bob", "message": "  "}).status_code == 400


def test_download_endpoint_rejects_non_cdn_urls(client):
    r = client.post("/api/download", json={"urls": ["https://evil.com/x.jpg"], "name": "x"})
    assert r.status_code == 400


def test_run_rejects_empty_and_unknown(client):
    assert client.post("/api/run", json={"target": "a", "calls": []}).status_code == 400
    assert client.post("/api/run", json={"target": "a", "calls": [{"name": "__init__"}]}).status_code == 400


def test_run_previews_hidden_from_model_but_shown_to_user(client):
    # The user-facing result keeps previews; _truncate_for_model drops them.
    r = client.post("/api/run", json={"target": "a", "calls": [{"name": "get_media_type"}]}).json()
    result = r["tool_calls"][0]["result"]
    assert "previews" in result
    assert "previews" not in appmod._truncate_for_model(result)


def test_query_runs_model_and_records_history(client):
    r = client.post("/api/query", json={"target": "bob", "message": "quanti follower?"})
    assert r.status_code == 200 and r.json()["answer"] == "fatto"
    assert [e["value"] for e in client.get("/api/history/queries").json()] == ["quanti follower?"]
    assert [e["value"] for e in client.get("/api/history/targets").json()] == ["bob"]


def test_query_unknown_target_is_404_and_not_recorded(client):
    assert client.post("/api/query", json={"target": "nobody", "message": "x"}).status_code == 404
    assert client.get("/api/history/targets").json() == []


def test_history_delete_and_unknown_kind(client):
    client.post("/api/run", json={"target": "alice", "calls": [{"name": "get_user_info"}]})
    assert client.delete("/api/history/targets", params={"value": "alice"}).json() == []
    assert client.get("/api/history/nope").status_code == 404


def test_cancel_endpoint_stops_a_running_search(tmp_path, monkeypatch):
    """The whole point: /api/cancel must reach the worker while it runs, so it
    stops making (paid) backend calls instead of running to completion."""
    import threading

    import src.osint_service as svcmod

    history.targets.path = tmp_path / "t.json"
    history.queries.path = tmp_path / "q.json"
    running = threading.Event()
    calls = []

    class FakeApi:
        cache_store = cache_ttl_seconds = max_calls = on_call = None
        cancelled = None

    api = FakeApi()

    def slow_tool(**kwargs):
        """Stands in for a long scan: one 'request' per loop, checking the
        stop flag exactly like _CountingApiProxy does."""
        running.set()
        for _ in range(1000):
            if api.cancelled is not None and api.cancelled.is_set():
                raise svcmod.QueryCancelledError("stopped")
            calls.append(1)
            time.sleep(0.005)
        return {"done": True}

    monkeypatch.setattr(appmod, "build_service", lambda target: types.SimpleNamespace(
        api=api, target=target, target_id=1, backend_name="fake", api_call_count=len(calls),
        user={"username": target}, get_user_info=slow_tool))

    client = TestClient(appmod.app)
    result = {}

    def run():
        result["response"] = client.post(
            "/api/run", json={"target": "a", "run_id": "run-1", "calls": [{"name": "get_user_info"}]})

    worker = threading.Thread(target=run)
    worker.start()
    assert running.wait(timeout=5), "the run never started"
    time.sleep(0.05)
    assert client.post("/api/cancel", json={"run_id": "run-1"}).json() == {"cancelled": True}
    worker.join(timeout=5)
    assert not worker.is_alive(), "cancelling did not end the run"

    spent_at_cancel = len(calls)
    time.sleep(0.1)
    assert len(calls) == spent_at_cancel  # nothing more was spent after the stop
    assert len(calls) < 1000  # and it did not run to completion


def test_estimate_endpoint(client, monkeypatch):
    # The estimate needs the profile counters, so give the fake one.
    def fake_build(target):
        class FakeApi:
            cache_store = cache_ttl_seconds = max_calls = on_call = cancelled = None
        return types.SimpleNamespace(
            api=FakeApi(), target=target, target_id=1, backend_name="fake", api_call_count=1,
            user={"username": target, "media_count": 60, "follower_count": 500, "following_count": 100})

    monkeypatch.setattr(appmod, "build_service", fake_build)
    r = client.post("/api/estimate", json={"target": "a", "calls": [
        {"name": "get_user_info"}, {"name": "get_followers", "args": {"limit": 100}}]})
    assert r.status_code == 200
    data = r.json()
    assert data["total_high"] >= data["total_low"] > 0
    assert [c["name"] for c in data["per_command"]] == ["get_user_info", "get_followers"]
    assert data["profile"]["follower_count"] == 500


def test_estimate_requires_commands(client):
    assert client.post("/api/estimate", json={"target": "a", "calls": []}).status_code == 400


def test_cancel_unknown_run_is_harmless(client):
    assert client.post("/api/cancel", json={"run_id": "nope"}).json() == {"cancelled": False}


def test_dossier_save_list_open_diff_delete(client, tmp_path, monkeypatch):
    from src.web import dossier
    monkeypatch.setattr(dossier, "DOSSIER_DIR", tmp_path / "dossier")

    first = client.post("/api/dossier", json={"target": "alice", "mode": "base", "results": [
        {"name": "get_followers", "result": [{"id": "1", "username": "anna"}]}]}).json()
    second = client.post("/api/dossier", json={"target": "alice", "mode": "base", "results": [
        {"name": "get_followers", "result": [{"id": "2", "username": "bruno"}]}]}).json()
    assert first["id"] and second["id"]

    listed = client.get("/api/dossier", params={"target": "alice"}).json()
    assert len(listed) == 2

    reopened = client.get(f"/api/dossier/alice/{second['id']}").json()
    assert reopened["results"][0]["result"][0]["username"] == "bruno"

    diff = client.get(f"/api/dossier/alice/{first['id']}/diff/{second['id']}").json()
    entry = diff["commands"][0]
    assert entry["added"] == ["bruno"] and entry["removed"] == ["anna"]

    assert client.delete(f"/api/dossier/alice/{first['id']}").json() == {"deleted": True}
    assert len(client.get("/api/dossier", params={"target": "alice"}).json()) == 1


def test_dossier_requires_a_target(client):
    assert client.post("/api/dossier", json={"results": []}).status_code == 400


def test_dossier_missing_is_404(client, tmp_path, monkeypatch):
    from src.web import dossier
    monkeypatch.setattr(dossier, "DOSSIER_DIR", tmp_path / "dossier")
    assert client.get("/api/dossier/alice/nope").status_code == 404


def test_cache_clear_endpoint(client):
    assert "cleared" in client.delete("/api/cache").json()


def test_about_endpoint(client):
    data = client.get("/api/about").json()
    assert data["version"] and data["author"]
    assert any(lib["name"] == "fastapi" for lib in data["libraries"])


def test_security_headers(client):
    h = client.get("/api/tools").headers
    assert h["cache-control"] == "no-store"
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "no-referrer"


def test_account_about_is_exposed_as_its_own_command(client):
    """It costs an extra request, so it must be a command the user picks
    deliberately - not a silent second lookup inside get_user_info."""
    specs = {s["name"]: s for s in client.get("/api/tools").json()}
    assert "get_account_about" in specs
    assert specs["get_account_about"]["params"] == []
    assert specs["get_account_about"]["needs_target"] is True

    from src.web import cost
    assert cost.estimate_command("get_account_about", {}, {}) == (1, 1)
    assert cost.estimate_command("get_user_info", {}, {}) == (0, 0)  # still free
