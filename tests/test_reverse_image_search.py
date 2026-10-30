"""Unit tests for Reverse Image Search Helper."""
from unittest.mock import MagicMock

import pytest

from src.osint_service import HikerAPIError, OsintgramService, OsintServiceError
from src.reverse_image_search import (
    ReverseImageSearchEngine,
    build_reverse_search_urls,
)
from src.web.tools import build_tools, tool_specs


def test_build_reverse_search_urls():
    url = "https://instagram.fcdn.net/v/t51/avatar.jpg?token=abc"
    urls = build_reverse_search_urls(url)

    assert "lens.google.com" in urls["google_lens"]
    assert "yandex.com/images" in urls["yandex"]
    assert "bing.com/images" in urls["bing"]
    assert "tineye.com" in urls["tineye"]
    assert "baidu.com" in urls["baidu"]

    # Biometric facial indexing services dropped per review feedback
    assert "facecheck" not in urls
    assert "pimeyes" not in urls

    # Empty url handling
    assert build_reverse_search_urls("") == {}
    assert build_reverse_search_urls(None) == {}


def test_reverse_image_search_engine():
    engine = ReverseImageSearchEngine()
    url = "https://cdn.example.com/photo.jpg"
    res = engine.analyze(image_url=url, context="avatar")

    assert res["image_url"] == url
    assert res["context"] == "avatar"
    assert "google_lens" in res["search_engines"]
    assert "yandex" in res["engine_labels"]
    assert "expiry_warning" in res


def test_osint_service_get_reverse_image_search_explicit_url():
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {
        "user": {"pk": "100", "username": "alice", "is_private": False}
    }
    service = OsintgramService("alice", mock_api)

    explicit_url = "https://cdn.example.com/custom.jpg"
    res = service.get_reverse_image_search(photo_url=explicit_url)
    assert res["image_url"] == explicit_url
    assert res["context"] == "media_photo"
    assert "google_lens" in res["search_engines"]


def test_osint_service_invalid_photo_url_rejected():
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {
        "user": {"pk": "100", "username": "alice", "is_private": False}
    }
    service = OsintgramService("alice", mock_api)

    for invalid in ["javascript:alert(1)", "file:///etc/passwd", "not-a-url", "ftp://example.com/img.jpg"]:
        with pytest.raises(OsintServiceError):
            service.get_reverse_image_search(photo_url=invalid)


def test_osint_service_get_reverse_image_search_fallback_propic():
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {
        "user": {
            "pk": "100",
            "username": "alice",
            "profile_pic_url": "https://cdn.example.com/avatar_hd.jpg",
            "is_private": False,
        }
    }
    service = OsintgramService("alice", mock_api)

    res = service.get_reverse_image_search()
    assert res["image_url"] == "https://cdn.example.com/avatar_hd.jpg"
    assert res["context"] == "profile_pic"


def test_osint_service_propic_error_classification():
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {
        "user": {"pk": "100", "username": "alice", "profile_pic_url": "https://cdn.example.com/saved.jpg", "is_private": False}
    }
    service = OsintgramService("alice", mock_api)

    # When get_user_propic raises HikerAPIError, it gracefully falls back to user profile_pic_url
    service.get_user_propic = MagicMock(side_effect=HikerAPIError("propic endpoint 404"))
    res = service.get_reverse_image_search()
    assert res["image_url"] == "https://cdn.example.com/saved.jpg"

    # When get_user_propic raises an unexpected exception (e.g. ValueError or connection crash), it is raised
    service.get_user_propic = MagicMock(side_effect=RuntimeError("unexpected crash"))
    with pytest.raises(RuntimeError):
        service.get_reverse_image_search()


def test_osint_service_get_reverse_image_search_no_pic_error():
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {
        "user": {"pk": "100", "username": "alice", "profile_pic_url": None, "is_private": False}
    }
    service = OsintgramService("alice", mock_api)

    with pytest.raises(OsintServiceError):
        service.get_reverse_image_search()


def test_reverse_image_search_tool_specs():
    specs = tool_specs()
    spec = next((s for s in specs if s["name"] == "get_reverse_image_search"), None)
    assert spec is not None
    assert any(p["name"] == "photo_url" for p in spec["params"])

    mock_service = MagicMock()
    mock_service.get_reverse_image_search.return_value = {"search_engines": {"yandex": "https://yandex.com"}}
    tools = build_tools(mock_service)
    tool_fn = next((t for t in tools if t.__name__ == "get_reverse_image_search"), None)
    assert tool_fn is not None
    output = tool_fn()
    assert "yandex" in output
