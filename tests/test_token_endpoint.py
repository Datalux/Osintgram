"""Tests for entering the HikerAPI key from the web UI.

Nothing here talks to HikerAPI: check_hiker_token is stubbed, so no token,
quota or network is needed.
"""
import pytest
from fastapi.testclient import TestClient

import src.osint_service as svcmod
import src.web.app as appmod


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("HIKERAPI_TOKEN", raising=False)
    svcmod.set_runtime_hiker_token(None)
    # Point both the reader and the writer at a throwaway credentials file.
    creds = tmp_path / "credentials.ini"
    monkeypatch.setattr(svcmod.resolve_hiker_token, "__defaults__", (str(creds),))
    monkeypatch.setattr(svcmod.hiker_token_source, "__defaults__", (str(creds),))
    monkeypatch.setattr(svcmod.save_hiker_token, "__defaults__", (str(creds),))
    monkeypatch.setattr(appmod, "check_hiker_token",
                        lambda token: {"requests": 474, "amount": 1.5, "currency": "USD"}
                        if token == "hik_valid_key_0000" else _reject())
    # base_url matters: TestClient defaults to Host "testserver", which the
    # endpoint refuses on purpose (see test_a_remote_host_header_cannot_set_the_key).
    yield TestClient(appmod.app, base_url="http://127.0.0.1:8000"), creds
    svcmod.set_runtime_hiker_token(None)


def _reject():
    raise svcmod.HikerAPIError("401 Unauthorized")


def test_reports_no_key_when_nothing_is_configured(client):
    api, _ = client
    assert api.get("/api/token").json() == {
        "configured": False, "source": None, "locked": False, "preview": None}


def test_accepting_a_key_validates_it_and_saves_it(client):
    api, creds = client
    r = api.post("/api/token", json={"token": "hik_valid_key_0000", "remember": True})
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True and body["saved"] is True
    assert body["balance"]["requests"] == 474
    # Usable straight away, and written where the CLI reads it too.
    assert svcmod.resolve_hiker_token(str(creds)) == "hik_valid_key_0000"
    assert "hik_valid_key_0000" in creds.read_text()


def test_the_key_is_never_returned_only_masked(client):
    api, _ = client
    body = api.post("/api/token", json={"token": "hik_valid_key_0000"}).json()
    assert body["preview"] == "hik_…0000"
    assert "hik_valid_key_0000" not in str(body)
    # ...and not by the read endpoint either.
    assert "hik_valid_key_0000" not in str(api.get("/api/token").json())


def test_a_bad_key_is_rejected_before_being_stored(client):
    api, creds = client
    r = api.post("/api/token", json={"token": "sbagliata", "remember": True})
    assert r.status_code == 400
    assert "401" in r.json()["detail"]
    assert svcmod.resolve_hiker_token(str(creds)) is None
    assert not creds.exists()  # nothing written for a key that doesn't work


def test_remember_false_keeps_the_key_out_of_the_file(client):
    api, creds = client
    body = api.post("/api/token", json={"token": "hik_valid_key_0000", "remember": False}).json()
    assert body["saved"] is False and body["source"] == "runtime"
    assert not creds.exists()


def test_env_token_wins_and_is_reported_as_locked(client, monkeypatch):
    api, _ = client
    monkeypatch.setenv("HIKERAPI_TOKEN", "env_key_abcdefgh")
    api.post("/api/token", json={"token": "hik_valid_key_0000", "remember": False})
    state = api.get("/api/token").json()
    assert state["source"] == "env" and state["locked"] is True
    assert state["preview"] == "env_…efgh"


def test_clearing_forgets_the_session_key(client):
    api, _ = client
    api.post("/api/token", json={"token": "hik_valid_key_0000", "remember": False})
    assert api.delete("/api/token").json()["configured"] is False


def test_a_remote_host_header_cannot_set_the_key(client):
    """DNS-rebinding defence: this endpoint only answers to localhost."""
    api, _ = client
    for headers in ({"host": "attacker.example"}, {"host": "127.0.0.1:8000", "origin": "https://evil.test"}):
        r = api.post("/api/token", json={"token": "hik_valid_key_0000"}, headers=headers)
        assert r.status_code == 403
    assert api.delete("/api/token", headers={"host": "attacker.example"}).status_code == 403


def test_local_hosts_are_accepted(client):
    api, _ = client
    for host in ("localhost:8000", "127.0.0.1:8000", "[::1]:8000"):
        r = api.post("/api/token", json={"token": "hik_valid_key_0000", "remember": False},
                     headers={"host": host, "origin": f"http://{host}"})
        assert r.status_code == 200, host
