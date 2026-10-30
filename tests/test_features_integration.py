import pytest
from fastapi.testclient import TestClient

import src.web.app as appmod
from src.osint_service import OsintgramService


@pytest.fixture
def api_client():
    return TestClient(appmod.app, base_url="http://127.0.0.1:8000")


def test_export_graph_endpoint_gexf(api_client):
    payload = {
        "target": "target_user",
        "results": [
            {"name": "get_followers", "result": [{"username": "alice", "id": "1"}]},
            {"name": "get_followings", "result": [{"username": "bob", "id": "2"}]},
        ],
        "format": "gexf",
    }
    resp = api_client.post("/api/export/graph", json=payload)
    assert resp.status_code == 200
    assert "application/xml" in resp.headers.get("content-type", "")
    assert 'attachment; filename="target_user_network.gexf"' in resp.headers.get("content-disposition", "")
    content = resp.text
    assert "<gexf" in content
    assert 'id="alice"' in content
    assert 'id="bob"' in content


def test_export_graph_endpoint_json(api_client):
    payload = {
        "target": "target_user",
        "results": [
            {"name": "get_followers", "result": [{"username": "alice", "id": "1"}]},
        ],
        "format": "json",
    }
    resp = api_client.post("/api/export/graph", json=payload)
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")
    data = resp.json()
    assert data["target"] == "target_user"
    assert data["stats"]["node_count"] == 2
    assert data["stats"]["edge_count"] == 1


def test_export_graph_endpoint_cytoscape(api_client):
    payload = {
        "target": "target_user",
        "results": [
            {"name": "get_followers", "result": [{"username": "alice", "id": "1"}]},
        ],
        "format": "cytoscape",
    }
    resp = api_client.post("/api/export/graph", json=payload)
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")
    data = resp.json()
    assert data["format"] == "cytoscape"
    assert "elements" in data
    assert len(data["elements"]["nodes"]) == 2


def test_export_graph_endpoint_vis(api_client):
    payload = {
        "target": "target_user",
        "results": [
            {"name": "get_followers", "result": [{"username": "alice", "id": "1"}]},
        ],
        "format": "vis",
    }
    resp = api_client.post("/api/export/graph", json=payload)
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")
    data = resp.json()
    assert data["format"] == "vis"
    assert len(data["nodes"]) == 2


def test_websearch_api_endpoints(api_client):
    headers = {"origin": "http://127.0.0.1:8000"}
    # GET settings
    get_resp = api_client.get("/api/ai/websearch")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "enabled" in data
    assert "provider" in data

    # POST settings
    post_resp = api_client.post(
        "/api/ai/websearch",
        json={"enabled": True, "provider": "wikipedia", "remember": False},
        headers=headers,
    )
    assert post_resp.status_code == 200
    assert post_resp.json()["ok"] is True
    assert post_resp.json()["enabled"] is True
    assert post_resp.json()["provider"] == "wikipedia"

    # Verify updated
    get_resp_after = api_client.get("/api/ai/websearch")
    assert get_resp_after.json()["enabled"] is True
    assert get_resp_after.json()["provider"] == "wikipedia"


def test_proxy_api_endpoints(api_client):
    headers = {"origin": "http://127.0.0.1:8000"}
    # GET proxy settings
    resp = api_client.get("/api/proxy/settings")
    assert resp.status_code == 200
    assert "configured" in resp.json()

    # Clear proxy
    clear_resp = api_client.post(
        "/api/proxy/settings",
        json={"proxy": "", "remember": False},
        headers=headers,
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["configured"] is False


def test_stories_and_highlights_lossless_resolution():
    class FakeStoriesApi:
        def user_by_username_v2(self, username):
            return {"user": {"pk": 100, "username": username, "is_private": False}}

        def user_stories_v2(self, user_id):
            return {
                "reel": {
                    "items": [
                        {
                            "id": "story_photo_1",
                            "media_type": 1,
                            "image_versions2": {
                                "candidates": [
                                    {"url": "https://cdn.test/low.jpg", "width": 150, "height": 150},
                                    {"url": "https://cdn.test/high_res.jpg", "width": 1080, "height": 1920},
                                    {"url": "https://cdn.test/mid.jpg", "width": 640, "height": 1136},
                                ]
                            },
                        },
                        {
                            "id": "story_video_1",
                            "media_type": 2,
                            "image_versions2": {
                                "candidates": [
                                    {"url": "https://cdn.test/thumb.jpg", "width": 150, "height": 150},
                                ]
                            },
                            "video_versions": [
                                {"url": "https://cdn.test/low.mp4", "width": 360, "height": 640},
                                {"url": "https://cdn.test/hd.mp4", "width": 1080, "height": 1920},
                            ],
                        },
                    ]
                }
            }

        def user_highlights_v2(self, user_id):
            return {
                "response": {
                    "tray": [
                        {
                            "id": "highlight:9999",
                            "title": "Summer Trip",
                            "media_count": 5,
                            "cover_media": {
                                "cropped_image_version": {"url": "https://cdn.test/cropped.jpg"},
                                "full_image_version": {"url": "https://cdn.test/uncropped_full_res.jpg"},
                            },
                        }
                    ]
                }
            }

    service = OsintgramService("target_user", FakeStoriesApi())

    # Stories: should pick highest resolution candidate
    stories = service.get_user_stories()
    assert len(stories) == 2
    assert stories[0]["url"] == "https://cdn.test/high_res.jpg"
    assert stories[1]["url"] == "https://cdn.test/hd.mp4"

    # Highlights: should pick uncropped full_image_version
    highlights = service.get_highlights()
    assert len(highlights) == 1
    assert highlights[0]["url"] == "https://cdn.test/uncropped_full_res.jpg"


def test_privacy_guard_extended_protection():
    from src.web.web_search import validate_privacy_guard, _validate_searxng_url
    import pytest

    # Target username
    with pytest.raises(ValueError, match="target username"):
        validate_privacy_guard("info about target_alice", target_username="target_alice")

    # Extra identifier (e.g. full name)
    with pytest.raises(ValueError, match="target personal identifier"):
        validate_privacy_guard("where is Alice Wonder living", target_username="bob", extra_identifiers=["Alice Wonder"])

    # Email address
    with pytest.raises(ValueError, match="email"):
        validate_privacy_guard("contact john.doe@example.com", target_username="alice")

    # Valid query passes
    assert validate_privacy_guard("Eiffel Tower Paris history", target_username="john") == "Eiffel Tower Paris history"

    # SearXNG URL validation
    assert _validate_searxng_url("http://127.0.0.1:8888") == "http://127.0.0.1:8888"
    assert _validate_searxng_url("https://searx.example.com") == "https://searx.example.com"
    with pytest.raises(ValueError, match="http:// or https://"):
        _validate_searxng_url("ftp://searx.example.com")


def test_instagrapi_mask_proxy():
    from src.instagrapi_backend import mask_proxy
    assert mask_proxy("http://alice:secret123@10.0.0.1:8080") == "http://alice:***@10.0.0.1:8080"
    assert mask_proxy("socks5://user:pass@proxy.net:1080") == "socks5://user:***@proxy.net:1080"
    assert mask_proxy("http://10.0.0.1:8080") == "http://10.0.0.1:8080"
    assert mask_proxy("") == ""


def test_export_graph_security(api_client):
    # Reject non-local origin
    evil_resp = api_client.post(
        "/api/export/graph",
        json={"target": "alice", "results": []},
        headers={"origin": "http://evil.com"},
    )
    assert evil_resp.status_code == 403

    # Reject excessive results
    huge_resp = api_client.post(
        "/api/export/graph",
        json={"target": "alice", "results": list(range(10001))},
        headers={"origin": "http://127.0.0.1:8000"},
    )
    assert huge_resp.status_code == 400


def test_export_graph_invalid_format_returns_400(api_client):
    payload = {
        "target": "target_user",
        "results": [],
        "format": "invalid_format_xyz",
    }
    resp = api_client.post(
        "/api/export/graph",
        json=payload,
        headers={"origin": "http://127.0.0.1:8000"},
    )
    assert resp.status_code == 400
    assert "Unsupported format" in resp.json().get("detail", "")
    assert "Supported formats: gexf, json, cytoscape, vis" in resp.json().get("detail", "")
