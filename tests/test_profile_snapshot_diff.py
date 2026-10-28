import pytest
from fastapi.testclient import TestClient

import src.web.app as appmod
from src.osint_service import OsintgramService
from src.snapshot_tracker import (
    compute_avatar_hash,
    create_snapshot,
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
    # The helper above creates an in-memory entry; let's verify via get_db_connection
    # For testing persistent tables across calls, use a dedicated connection / test sqlite file
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
        "followers_sample": ["bob", "david", "grace"],  # charlie lost (unfollowed), grace joined
        "followings_sample": ["eve"],  # unfollowed frank
    }

    diff = compare_snapshots(snap1, snap2)
    assert diff["has_changes"] is True
    assert diff["target"] == "target_user"

    # Metric checks
    m = diff["metric_deltas"]
    assert m["followers"]["diff"] == 250
    assert m["followers"]["growth_percent"] == 25.0
    assert m["following"]["diff"] == -10
    assert m["posts"]["diff"] == 1

    # Structural changes
    fields = diff["field_changes"]
    assert "full_name" in fields
    assert fields["full_name"]["old"] == "Alice Old"
    assert fields["full_name"]["new"] == "Alice New"
    assert "biography" in fields
    assert "is_verified" in fields
    assert "avatar_hash" in fields

    # Link changes
    links = diff["link_changes"]
    assert "https://youtube.com/alice" in links["added"]
    assert "https://old.com" in links["removed"]

    # Network differential (unfollowers / new followers)
    net = diff["network_changes"]
    assert "charlie" in net["lost_followers"]
    assert "grace" in net["new_followers"]
    assert "frank" in net["unfollowed"]
    assert len(net["new_followings"]) == 0

    # Summary lines
    summary = " ".join(diff["summary"])
    assert "Followers: 1,000 → 1,250 (+250, +25.0%)" in summary
    assert "Profile picture was updated" in summary
    assert "charlie" in summary
    assert "grace" in summary


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


def test_webhook_payload_builders():
    diff_data = {
        "has_changes": True,
        "summary": ["Followers: +50 accounts", "Profile picture was updated"],
        "metric_deltas": {
            "followers": {"old": 100, "new": 150, "diff": 50},
            "following": {"old": 50, "new": 50, "diff": 0},
        },
        "network_changes": {
            "lost_followers": ["bad_bot_1", "bad_bot_2"],
            "new_followers": ["new_friend"],
        },
    }

    # Discord
    discord = build_discord_payload("target_alice", diff_data)
    assert "embeds" in discord
    assert len(discord["embeds"]) == 1
    assert "target_alice" in discord["embeds"][0]["title"]
    assert discord["embeds"][0]["color"] == 0xE1306C

    # Slack
    slack = build_slack_payload("target_alice", diff_data)
    assert "blocks" in slack
    assert len(slack["blocks"]) >= 2

    # Telegram
    tg = build_telegram_payload("target_alice", diff_data, chat_id="123456")
    assert tg["chat_id"] == "123456"
    assert "<b>Profile Change Detected: @target_alice</b>" in tg["text"]


def test_webhook_dispatch_mock(monkeypatch):
    class FakeResponse:
        status_code = 204
        text = ""

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json=None, headers=None):
            return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, "Client", FakeClient)

    res = dispatch_webhook("https://discord.com/api/webhooks/123/xyz", "test_event", {"summary": ["Hello"]})
    assert res["ok"] is True
    assert res["status_code"] == 204

    # Empty URL fails
    err_res = dispatch_webhook("", "test_event", {})
    assert err_res["ok"] is False


def test_snapshot_and_webhook_api_endpoints(api_client, tmp_path, monkeypatch):
    test_db = tmp_path / "test_snapshots.sqlite3"
    import src.snapshot_tracker as st
    monkeypatch.setattr(st, "DEFAULT_DB_PATH", test_db)

    headers = {"origin": "http://127.0.0.1:8000"}

    # Mock service for snapshot creation
    class FakeService:
        target = "test_user"
        target_id = 999
        is_private = False

        def get_profile_info(self):
            return {
                "username": "test_user",
                "full_name": "Test User",
                "biography": "Hello OSINT",
                "external_url": "https://example.com",
                "follower_count": 500,
                "following_count": 120,
                "media_count": 30,
            }

        def get_followers(self, limit=200):
            return [{"username": "user1"}, {"username": "user2"}]

        def get_followings(self, limit=200):
            return [{"username": "user3"}]

        def take_snapshot(self, include_network=False, limit_network=200):
            return st.create_snapshot("test_user", self.get_profile_info(), db_path=test_db)

    monkeypatch.setattr(appmod, "build_service", lambda target: FakeService())

    # 1. Create first snapshot
    post1 = api_client.post("/api/target/test_user/snapshot", json={"include_network": False}, headers=headers)
    assert post1.status_code == 200
    snap1_id = post1.json()["snapshot"]["id"]

    # 2. List snapshots
    list_resp = api_client.get("/api/target/test_user/snapshots")
    assert list_resp.status_code == 200
    snaps = list_resp.json()["snapshots"]
    assert len(snaps) == 1

    # 3. Create second snapshot with changes
    st.create_snapshot(
        "test_user",
        {
            "username": "test_user",
            "full_name": "Test User Updated",
            "biography": "New bio",
            "follower_count": 550,
            "following_count": 120,
            "media_count": 31,
        },
        db_path=test_db,
    )

    # 4. Get diff
    diff_resp = api_client.get("/api/target/test_user/diff")
    assert diff_resp.status_code == 200
    diff = diff_resp.json()["diff"]
    assert diff["has_changes"] is True
    assert diff["metric_deltas"]["followers"]["diff"] == 50

    # 5. Webhook test endpoint
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json=None, headers=None):
            class R:
                status_code = 200
                text = "ok"
            return R()

    import httpx
    monkeypatch.setattr(httpx, "Client", FakeClient)

    hook_resp = api_client.post(
        "/api/webhook/test",
        json={"webhook_url": "https://example.com/webhook", "target": "test_user"},
        headers=headers,
    )
    assert hook_resp.status_code == 200
    assert hook_resp.json()["ok"] is True
