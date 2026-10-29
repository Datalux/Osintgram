"""Unit tests for Reverse Image Search & Facial Pivot Helper."""
import io
from unittest.mock import MagicMock

import pytest
from PIL import Image

from src.osint_service import OsintgramService, OsintServiceError
from src.reverse_image_search import (
    ReverseImageSearchEngine,
    build_reverse_search_urls,
    compute_dhash,
    hamming_distance,
)
from src.web.tools import build_tools, tool_specs


def _create_test_image(color=(255, 0, 0), size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_build_reverse_search_urls():
    url = "https://instagram.fcdn.net/v/t51/avatar.jpg?token=abc"
    urls = build_reverse_search_urls(url)

    assert "lens.google.com" in urls["google_lens"]
    assert "yandex.com/images" in urls["yandex"]
    assert "bing.com/images" in urls["bing"]
    assert "tineye.com" in urls["tineye"]
    assert "baidu.com" in urls["baidu"]
    assert "facecheck.id" in urls["facecheck"]
    assert "pimeyes.com" in urls["pimeyes"]

    # Empty url handling
    assert build_reverse_search_urls("") == {}
    assert build_reverse_search_urls(None) == {}


def test_compute_dhash_and_hamming():
    img_bytes1 = _create_test_image(color=(255, 0, 0))
    img_bytes2 = _create_test_image(color=(255, 0, 0))

    hash1 = compute_dhash(img_bytes1)
    hash2 = compute_dhash(img_bytes2)

    assert hash1 is not None and len(hash1) == 16
    assert hash1 == hash2
    assert hamming_distance(hash1, hash2) == 0

    # Contrast image (left bright, right dark) vs solid
    img_contrast = Image.new("L", (64, 64))
    for x in range(64):
        for y in range(64):
            img_contrast.putpixel((x, y), (64 - x) * 3)
    buf = io.BytesIO()
    img_contrast.save(buf, format="PNG")
    hash_contrast = compute_dhash(buf.getvalue())

    assert hash_contrast is not None
    assert hash_contrast != hash1
    assert hamming_distance(hash1, hash_contrast) > 0


def test_reverse_image_search_engine():
    engine = ReverseImageSearchEngine()
    url = "https://cdn.example.com/photo.jpg"
    res = engine.analyze(image_url=url, context="avatar")

    assert res["image_url"] == url
    assert res["context"] == "avatar"
    assert "google_lens" in res["search_engines"]
    assert "yandex" in res["engine_labels"]


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
