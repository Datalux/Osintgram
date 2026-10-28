import io
import pytest
from fastapi.testclient import TestClient

import src.web.app as appmod
from src.snapshot_tracker import (
    compute_avatar_hash,
    create_snapshot,
    delete_snapshots,
    get_snapshot,
    list_snapshots,
    compare_snapshots,
    diff_latest_two,
    get_db_connection,
)
from src.webhook_dispatcher import (
    build_discord_payload,
    build_slack_payload,
    build_telegram_payload,
    dispatch_webhook,
    mask_webhook_url,
)


@pytest.fixture
def mem_db():
    conn = get_db_connection(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def api_client():
    return TestClient(appmod.app, base_url="http://127.0.0.1:8000")


def test_avatar_hash():
    h1 = compute_avatar_hash("https://cdn.example.com/avatar1.jpg")
    h2 = compute_avatar_hash("https://cdn.example.com/avatar1.jpg")
    h3 = compute_avatar_hash("https://cdn.example.com/avatar2.jpg")
    assert h1 == h2
    assert h1 != h3
    assert compute_avatar_hash("") == ""
    assert compute_avatar_hash(None) == ""


def test_avatar_hash_signed_query_strip_and_bytes():
    # Instagram signed CDN URLs change parameters on every query
    url1 = "https://instagram.fcdn.net/v/t51/avatar.jpg?stp=dst-jpg&token=abc123"
    url2 = "https://instagram.fcdn.net/v/t51/avatar.jpg?stp=dst-jpg&token=xyz999&expires=888"
    assert compute_avatar_hash(url1) == compute_avatar_hash(url2)

    # Bytes hashing
    b1 = b"raw_image_bytes_here"
    b2 = b"raw_image_bytes_here"
    b3 = b"different_image_bytes"
    assert compute_avatar_hash(b1) == compute_avatar_hash(b2)
    assert compute_avatar_hash(b1) != compute_avatar_hash(b3)


def test_snapshot_crud(mem_db):
    profile_data = {
        "username": "test_target",
        "full_name": "Test User",
        "biography": "Initial bio",
        "external_url": "https://example.com",
        "profile_pic_url": "https://cdn.example.com/pic1.jpg",
        "follower_count": 1000,
        "following_count": 250,
        "media_count": 50,
        "is_private": False,
        "is_verified": False,
        "bio_links": ["https://example.com", "https://linktr.ee/target"],
    }
    followers = [{"username": "alice"}, {"username": "bob"}]
    followings = [{"username": "charlie"}, {"username": "dave"}]

    snap = create_snapshot(
        target="test_target",
        profile_data=profile_data,
        followers=followers,
        followings=followings,
        db_path=":memory:",
    )
    assert snap["target"] == "test_target"
    assert snap["follower_count"] == 1000
    assert snap["avatar_hash"] != ""


def test_compare_snapshots_text_and_metrics():
    snap1 = {
        "id": 1,
        "target": "target_user",
        "timestamp": "2026-01-01T10:00:00Z",
        "username": "target_user",
        "full_name": "Alice Old",
        "biography": "Old bio",
        "external_url": "https://old.com",
        "avatar_hash": "hash_aaa",
        "follower_count": 1000,
        "following_count": 200,
        "media_count": 15,
        "is_private": 0,
        "is_verified": 0,
        "bio_links": ["https://old.com"],
        "followers_sample": ["bob", "charlie", "david"],
        "followings_sample": ["eve", "frank"],
    }

    snap2 = {
        "id": 2,
        "target": "target_user",
        "timestamp": "2026-01-05T10:00:00Z",
        "username": "target_user",
        "full_name": "Alice New",
        "biography": "New bio updated",
        "external_url": "https://new.com",
        "avatar_hash": "hash_bbb",
        "follower_count": 1250,
        "following_count": 190,
        "media_count": 16,
        "is_private": 0,
        "is_verified": 1,
        "bio_links": ["https://new.com", "https://youtube.com/alice"],
        "followers_sample": ["bob", "david", "grace"],
        "followings_sample": ["eve"],
    }

    diff = compare_snapshots(snap1, snap2)
    assert diff["has_changes"] is True
    assert diff["target"] == "target_user"

    m = diff["metric_deltas"]
    assert m["followers"]["diff"] == 250
    assert m["followers"]["growth_percent"] == 25.0
    assert m["following"]["diff"] == -10
    assert m["posts"]["diff"] == 1

    fields = diff["field_changes"]
    assert fields["full_name"]["old"] == "Alice Old"
    assert fields["full_name"]["new"] == "Alice New"

    links = diff["link_changes"]
    assert "https://youtube.com/alice" in links["added"]
    assert "https://old.com" in links["removed"]

    net = diff["network_changes"]
    assert "charlie" in net["lost_followers"]
    assert "grace" in net["new_followers"]
    assert "frank" in net["unfollowed"]

    summary = " ".join(diff["summary"])
    assert "Followers: 1,000 → 1,250 (+250, +25.0%)" in summary
    assert "charlie" in summary
    assert "grace" in summary


def test_untracked_and_truncated_network_sample():
    # 1. When followers_sample is None on one snapshot (include_network was False),
    # it must NOT report all followers as lost!
    snap_without_network = {
        "id": 1,
        "target": "alice",
        "follower_count": 500,
        "following_count": 100,
        "followers_sample": None,
        "followings_sample": None,
    }
    snap_with_network = {
        "id": 2,
        "target": "alice",
        "follower_count": 510,
        "following_count": 100,
        "followers_sample": ["bob", "charlie"],
        "followings_sample": ["dave"],
    }

    diff = compare_snapshots(snap_without_network, snap_with_network)
    net = diff["network_changes"]
    assert net["has_sample"] is False
    assert len(net["lost_followers"]) == 0
    assert len(net["new_followers"]) == 0
    # No false claims of unfollowers
    assert not any("unfollowers" in s.lower() for s in diff["summary"])

    # 2. Truncated network sample (e.g. 2 sampled out of 500 total followers)
    snap1_sampled = {
        "id": 3,
        "target": "alice",
        "follower_count": 500,
        "following_count": 100,
        "followers_sample": ["bob", "charlie"],
        "followings_sample": ["dave"],
    }
    snap2_sampled = {
        "id": 4,
        "target": "alice",
        "follower_count": 500,
        "following_count": 100,
        "followers_sample": ["bob", "frank"],
        "followings_sample": ["dave"],
    }
    diff_truncated = compare_snapshots(snap1_sampled, snap2_sampled)
    net_trunc = diff_truncated["network_changes"]
    assert net_trunc["has_sample"] is True
    assert net_trunc["is_partial"] is True
    summary_trunc = " ".join(diff_truncated["summary"])
    assert "partial" in summary_trunc.lower()


def test_compare_snapshots_no_changes():
    snap = {
        "id": 1,
        "target": "target_user",
        "timestamp": "2026-01-01T10:00:00Z",
        "username": "target_user",
        "full_name": "Target",
        "biography": "Bio",
        "external_url": "",
        "avatar_hash": "hash_123",
        "follower_count": 500,
        "following_count": 100,
        "media_count": 10,
        "is_private": 0,
        "is_verified": 0,
        "bio_links": [],
        "followers_sample": ["a", "b"],
        "followings_sample": ["c"],
    }
    diff = compare_snapshots(snap, dict(snap))
    assert diff["has_changes"] is False
    assert len(diff["summary"]) == 0


def test_webhook_hostile_input_escaping():
    hostile_diff = {
        "has_changes": True,
        "summary": ["Bio changed: '<script>alert(1)</script>' → '<b>hacked</b> & win'"],
        "metric_deltas": {},
        "network_changes": {},
    }

    # Telegram HTML escaping
    tg = build_telegram_payload("<script>evil</script>", hostile_diff, chat_id="12345")
    assert "<script>" not in tg["text"]
    assert "&lt;script&gt;evil&lt;/script&gt;" in tg["text"]
    assert "&lt;b&gt;hacked&lt;/b&gt; &amp; win" in tg["text"]

    # Slack mrkdwn escaping
    slack = build_slack_payload("<bad_user>&co", hostile_diff)
    slack_text = str(slack)
    assert "<bad_user>" not in slack_text
    assert "&lt;bad_user&gt;&amp;co" in slack_text


def test_webhook_ssrf_and_private_address_blocking():
    fake_diff = {"summary": ["test"]}

    # Non-https rejected
    r_http = dispatch_webhook("http://example.com/hook", "ev", fake_diff)
    assert r_http["ok"] is False
    assert "https://" in r_http["error"]

    # Localhost rejected
    r_lh = dispatch_webhook("https://localhost/hook", "ev", fake_diff)
    assert r_lh["ok"] is False
    assert "blocked" in r_lh["error"].lower()

    # Loopback IP rejected
    r_loop = dispatch_webhook("https://127.0.0.1:8080/hook", "ev", fake_diff)
    assert r_loop["ok"] is False
    assert "blocked" in r_loop["error"].lower()

    # Private RFC1918 IP rejected
    r_priv = dispatch_webhook("https://192.168.1.50/hook", "ev", fake_diff)
    assert r_priv["ok"] is False
    assert "blocked" in r_priv["error"].lower()


def test_webhook_url_masking():
    url_discord = "https://discord.com/api/webhooks/123456789/SuperSecretTokenXYZ"
    masked = mask_webhook_url(url_discord)
    assert "SuperSecretTokenXYZ" not in masked
    assert "***" in masked


def test_snapshot_deletion_and_api(api_client, tmp_path, monkeypatch):
    test_db = tmp_path / "test_snapshots.sqlite3"
    import src.snapshot_tracker as st
    monkeypatch.setattr(st, "DEFAULT_DB_PATH", test_db)

    headers = {"origin": "http://127.0.0.1:8000"}

    # Seed 2 snapshots
    st.create_snapshot("test_del_target", {"username": "test_del_target"}, db_path=test_db)
    st.create_snapshot("test_del_target", {"username": "test_del_target"}, db_path=test_db)
    assert len(st.list_snapshots("test_del_target", db_path=test_db)) == 2

    # Delete via API
    del_resp = api_client.delete("/api/target/test_del_target/snapshots", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted_count"] == 2
    assert len(st.list_snapshots("test_del_target", db_path=test_db)) == 0

    # Non-local origin rejected with 403
    forbidden_resp = api_client.delete(
        "/api/target/test_del_target/snapshots",
        headers={"origin": "http://evil-tracker.com"},
    )
    assert forbidden_resp.status_code == 403
