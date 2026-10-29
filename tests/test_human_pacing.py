"""Unit and integration tests for Adaptive Rate Limiting & Backoff engine."""
import configparser
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from src.human_pacing import (
    HumanPacer,
    PacingConfig,
    PacingMode,
    get_shared_pacer,
    reset_shared_pacer,
    resolve_pacing_config,
)
from src.osint_service import OsintgramService
from src.web.app import app


@pytest.fixture
def test_client():
    return TestClient(app, base_url="http://127.0.0.1:8000")


def test_pacing_config_defaults():
    cfg = PacingConfig()
    assert cfg.mode == PacingMode.NORMAL
    assert cfg.min_delay == 1.2
    assert cfg.max_delay == 2.6
    assert cfg.break_frequency == 25
    assert cfg.break_min == 10.0
    assert cfg.break_max == 20.0
    assert cfg.adaptive_backoff is True


def test_resolve_pacing_config_from_env(monkeypatch):
    monkeypatch.setenv("SCRAPE_PACING", "conservative")
    cfg = resolve_pacing_config()
    assert cfg.mode == PacingMode.CONSERVATIVE

    # Backwards-compatible alias
    monkeypatch.setenv("SCRAPE_PACING", "stealth")
    cfg = resolve_pacing_config()
    assert cfg.mode == PacingMode.CONSERVATIVE

    monkeypatch.delenv("SCRAPE_PACING", raising=False)
    monkeypatch.setenv("OSINTGRAM_PACING", "fast")
    cfg = resolve_pacing_config()
    assert cfg.mode == PacingMode.FAST


def test_resolve_pacing_config_from_ini(tmp_path, monkeypatch):
    monkeypatch.delenv("SCRAPE_PACING", raising=False)
    monkeypatch.delenv("OSINTGRAM_PACING", raising=False)
    ini_file = tmp_path / "credentials.ini"
    cp = configparser.ConfigParser()
    cp.add_section("Pacing")
    cp.set("Pacing", "mode", "custom")
    cp.set("Pacing", "min_delay", "2.0")
    cp.set("Pacing", "max_delay", "5.0")
    cp.set("Pacing", "break_frequency", "10")
    cp.set("Pacing", "break_min", "15.0")
    cp.set("Pacing", "break_max", "25.0")
    cp.set("Pacing", "adaptive_backoff", "false")
    with open(ini_file, "w") as f:
        cp.write(f)

    monkeypatch.setattr("src.human_pacing.CREDENTIALS_PATH", ini_file)
    cfg = resolve_pacing_config()
    assert cfg.mode == PacingMode.CUSTOM
    assert cfg.min_delay == 2.0
    assert cfg.max_delay == 5.0
    assert cfg.break_frequency == 10
    assert cfg.break_min == 15.0
    assert cfg.break_max == 25.0
    assert cfg.adaptive_backoff is False


def test_resolve_pacing_config_partial_invalid_ini(tmp_path, monkeypatch):
    monkeypatch.delenv("SCRAPE_PACING", raising=False)
    monkeypatch.delenv("OSINTGRAM_PACING", raising=False)
    ini_file = tmp_path / "credentials.ini"
    cp = configparser.ConfigParser()
    cp.add_section("Pacing")
    cp.set("Pacing", "mode", "invalid_mode_xyz")
    cp.set("Pacing", "min_delay", "not_a_number")
    cp.set("Pacing", "max_delay", "4.5")
    cp.set("Pacing", "break_frequency", "15")
    with open(ini_file, "w") as f:
        cp.write(f)

    monkeypatch.setattr("src.human_pacing.CREDENTIALS_PATH", ini_file)
    cfg = resolve_pacing_config()
    # Invalid mode and min_delay ignored, valid max_delay and break_frequency preserved
    assert cfg.mode == PacingMode.NORMAL
    assert cfg.min_delay == 1.2
    assert cfg.max_delay == 4.5
    assert cfg.break_frequency == 15


def test_human_pacer_first_request_and_fast_mode():
    sleeps = []
    pacer = HumanPacer(config=PacingConfig(mode=PacingMode.FAST), sleep_fn=sleeps.append)
    d1 = pacer.pace(is_subsequent=False)
    assert d1 == 0.05
    assert sleeps == [0.05]

    d2 = pacer.pace(is_subsequent=True)
    assert d2 == 0.05
    assert len(sleeps) == 2


def test_human_pacer_normal_distribution_bounds():
    sleeps = []
    cfg = PacingConfig(mode=PacingMode.NORMAL, break_frequency=0)
    pacer = HumanPacer(config=cfg, sleep_fn=sleeps.append)

    for _ in range(50):
        d = pacer.compute_delay(is_subsequent=True)
        assert 1.2 <= d <= 2.6, f"Delay {d} out of normal bounds [1.2, 2.6]"


def test_human_pacer_conservative_distribution_bounds():
    sleeps = []
    cfg = PacingConfig(mode=PacingMode.CONSERVATIVE, break_frequency=0)
    pacer = HumanPacer(config=cfg, sleep_fn=sleeps.append)

    for _ in range(50):
        d = pacer.compute_delay(is_subsequent=True)
        assert 2.0 <= d <= 4.8, f"Delay {d} out of conservative bounds [2.0, 4.8]"


def test_human_pacer_reading_breaks():
    sleeps = []
    cfg = PacingConfig(
        mode=PacingMode.CONSERVATIVE,
        break_frequency=3,
        break_min=10.0,
        break_max=15.0,
    )
    pacer = HumanPacer(config=cfg, sleep_fn=sleeps.append)

    # 1st request (subsequent)
    pacer.pace(is_subsequent=True)
    assert not pacer.is_on_break
    assert pacer.reading_breaks_taken == 0

    # 2nd request
    pacer.pace(is_subsequent=True)
    assert not pacer.is_on_break
    assert pacer.reading_breaks_taken == 0

    # 3rd request -> hits break_frequency 3!
    d3 = pacer.pace(is_subsequent=True)
    assert pacer.is_on_break
    assert pacer.reading_breaks_taken == 1
    assert d3 >= 10.0 + 2.0, f"Expected break delay, got {d3}"


def test_human_pacer_adaptive_backoff(monkeypatch):
    monkeypatch.setattr("random.gauss", lambda mu, sigma: mu)
    cfg = PacingConfig(mode=PacingMode.NORMAL, break_frequency=0, adaptive_backoff=True)
    pacer = HumanPacer(config=cfg, sleep_fn=lambda _: None)

    d_base = pacer.compute_delay(is_subsequent=True)
    assert d_base == 1.85

    pacer.record_throttle_or_error()
    pacer.record_throttle_or_error()
    assert pacer.consecutive_errors == 2

    # backoff_factor = 1.0 + 2 * 0.75 = 2.5 -> 1.85 * 2.5 = 4.625
    d_backed_off = pacer.compute_delay(is_subsequent=True)
    assert d_backed_off == 4.625

    # Decay on success
    pacer.record_success()
    assert pacer.consecutive_errors == 1
    pacer.record_success()
    assert pacer.consecutive_errors == 0
    pacer.record_success()
    assert pacer.consecutive_errors == 0


def test_human_pacer_telemetry_stats():
    sleeps = []
    cfg = PacingConfig(mode=PacingMode.NORMAL)
    pacer = HumanPacer(config=cfg, sleep_fn=sleeps.append)

    pacer.pace(is_subsequent=True)
    pacer.record_throttle_or_error()
    stats = pacer.get_stats()

    assert stats["mode"] == "normal"
    assert stats["requests_paced"] == 1
    assert stats["throttle_level"] == 1
    assert stats["total_delays_sec"] > 0
    assert stats["last_delay_sec"] > 0


def test_shared_pacer_persistence_across_scans():
    reset_shared_pacer()
    p1 = get_shared_pacer()
    p1.record_throttle_or_error()
    assert p1.consecutive_errors == 1

    p2 = get_shared_pacer()
    assert p2 is p1
    assert p2.consecutive_errors == 1
    reset_shared_pacer()


def test_osint_service_no_pacing_by_default_without_pacer():
    # Like HikerAPI backend: api_client has no pacer attribute
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {"user": {"pk": "12345", "username": "alice", "is_private": False}}
    mock_api.user_followers_g2.side_effect = [
        {"response": {"users": [{"pk": "1", "username": "bob"}]}, "next_page_id": "cursor_2"},
        {"response": {"users": [{"pk": "2", "username": "charlie"}]}, "next_page_id": None},
    ]

    service = OsintgramService("alice", mock_api)
    assert service.pacer is None
    followers = service.get_followers(limit=10)
    assert len(followers) == 2


def test_osint_service_pacing_integration():
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {"user": {"pk": "12345", "username": "alice", "is_private": False}}
    mock_api.user_followers_g2.side_effect = [
        {"response": {"users": [{"pk": "1", "username": "bob"}]}, "next_page_id": "cursor_2"},
        {"response": {"users": [{"pk": "2", "username": "charlie"}]}, "next_page_id": None},
    ]

    delays = []
    pacer = HumanPacer(
        config=PacingConfig(mode=PacingMode.NORMAL),
        sleep_fn=delays.append,
    )

    service = OsintgramService("alice", mock_api, pacer=pacer)
    followers = service.get_followers(limit=10)

    assert len(followers) == 2
    # Pacing called before the 2nd page
    assert len(delays) == 1
    assert delays[0] >= 1.2
    assert pacer.consecutive_errors == 0


def test_osint_service_pacing_backoff_on_throttle():
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {"user": {"pk": "12345", "username": "alice", "is_private": False}}
    mock_api.user_followers_g2.side_effect = [
        {"response": {"users": [{"pk": "1", "username": "bob"}]}, "next_page_id": "cursor_2"},
        RuntimeError("feedback_required: Please wait"),
    ]

    delays = []
    pacer = HumanPacer(
        config=PacingConfig(mode=PacingMode.NORMAL),
        sleep_fn=delays.append,
    )

    service = OsintgramService("alice", mock_api, pacer=pacer)
    followers = service.get_followers(limit=10)

    # Throttled gracefully with partial warning
    assert len(followers) == 1
    assert "feedback_required" in service.partial_warning
    # Pacer recorded throttle
    assert pacer.consecutive_errors == 1


def test_api_pacing_endpoints(test_client, tmp_path, monkeypatch):
    cred_file = tmp_path / "credentials.ini"
    monkeypatch.setattr("src.human_pacing.CREDENTIALS_PATH", cred_file)
    monkeypatch.delenv("SCRAPE_PACING", raising=False)
    monkeypatch.delenv("OSINTGRAM_PACING", raising=False)

    # 1. GET settings
    r = test_client.get("/api/pacing/settings")
    assert r.status_code == 200
    data = r.json()
    assert "mode" in data
    assert "min_delay" in data
    assert "adaptive_backoff" in data

    # 2. POST update to conservative (and stealth alias)
    r_post = test_client.post(
        "/api/pacing/settings",
        json={"mode": "conservative", "remember": True},
        headers={"origin": "http://127.0.0.1:8000"},
    )
    assert r_post.status_code == 200
    assert r_post.json()["mode"] == "conservative"
    assert cred_file.exists()
    assert "conservative" in cred_file.read_text()

    # Stealth alias maps to conservative
    r_post2 = test_client.post(
        "/api/pacing/settings",
        json={"mode": "stealth", "remember": True},
        headers={"origin": "http://127.0.0.1:8000"},
    )
    assert r_post2.status_code == 200
    assert r_post2.json()["mode"] == "conservative"

    # 3. Validation: negative delays reject
    r_neg = test_client.post(
        "/api/pacing/settings",
        json={"mode": "custom", "min_delay": -1.0, "max_delay": 2.0},
        headers={"origin": "http://127.0.0.1:8000"},
    )
    assert r_neg.status_code == 400

    # 4. Validation: min > max rejects
    r_inv = test_client.post(
        "/api/pacing/settings",
        json={"mode": "custom", "min_delay": 5.0, "max_delay": 2.0},
        headers={"origin": "http://127.0.0.1:8000"},
    )
    assert r_inv.status_code == 400

    # 5. Validation: min_delay = 0 in custom mode rejects
    r_zero = test_client.post(
        "/api/pacing/settings",
        json={"mode": "custom", "min_delay": 0.0, "max_delay": 2.0},
        headers={"origin": "http://127.0.0.1:8000"},
    )
    assert r_zero.status_code == 400

    # 6. Invalid mode rejects
    r_bad = test_client.post(
        "/api/pacing/settings",
        json={"mode": "ultra_fast_invalid"},
        headers={"origin": "http://127.0.0.1:8000"},
    )
    assert r_bad.status_code == 400

    # 7. Non-local origin rejected
    r_forbidden = test_client.post(
        "/api/pacing/settings",
        json={"mode": "normal"},
        headers={"origin": "http://evil-tracker.com"},
    )
    assert r_forbidden.status_code == 403
