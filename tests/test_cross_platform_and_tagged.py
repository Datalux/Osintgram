"""Tests for Cross-Platform Pivot and Tagged Posts deep dive."""
import pytest
from unittest.mock import patch

from src.web.cross_platform import (
    _check_github,
    scan_cross_platform,
    ALL_CHECKERS,
)
from src.osint_service import OsintgramService
from tests.conftest import user


def test_cross_platform_empty_username():
    res = scan_cross_platform("")
    assert res["target"] == ""
    assert res["found_count"] == 0
    assert res["platforms"] == []


def test_cross_platform_invalid_username_injection():
    # Path traversal / script / command injection characters
    bad_usernames = [
        "../../etc/passwd",
        "user; rm -rf",
        "<script>alert(1)</script>",
        "user\nname",
        "user/profile",
        "a" * 45,  # Exceeds max length 40
    ]
    for bad_user in bad_usernames:
        res = scan_cross_platform(bad_user)
        assert "error" in res
        assert "Invalid username" in res["error"]
        assert res["found_count"] == 0
        assert res["platforms"] == []


def test_cross_platform_status_distinction():
    def mock_found(username):
        return {
            "platform": "GitHub",
            "category": "Code & Development",
            "icon": "🐙",
            "url": f"https://github.com/{username}",
            "status": "found",
            "exists": True,
            "details": "10 repos",
        }

    def mock_error(username):
        return {
            "platform": "GitLab",
            "category": "Code & Development",
            "icon": "🦊",
            "url": f"https://gitlab.com/{username}",
            "status": "error",
            "exists": False,
            "details": "API rate limited or timeout",
        }

    def mock_not_found(username):
        return {
            "platform": "Telegram",
            "category": "Messaging",
            "icon": "✈️",
            "url": f"https://t.me/{username}",
            "status": "not_found",
            "exists": False,
            "details": "Not registered",
        }

    with patch("src.web.cross_platform.ALL_CHECKERS", [mock_found, mock_error, mock_not_found]):
        res = scan_cross_platform("testuser")
        assert res["target"] == "testuser"
        assert res["found_count"] == 1
        assert res["error_count"] == 1
        assert res["total_checked"] == 3
        assert len(res["platforms"]) == 3
        # Check ordering: found first, then error, then not_found
        assert res["platforms"][0]["status"] == "found"
        assert res["platforms"][1]["status"] == "error"
        assert res["platforms"][2]["status"] == "not_found"


def test_check_github_error_vs_not_found():
    # 200 -> found
    with patch("src.web.cross_platform._fetch", return_value=(200, b'{"name": "Octocat", "public_repos": 5}', {}, None)):
        res = _check_github("octocat")
        assert res["status"] == "found"
        assert res["exists"] is True
        assert "5 repos" in res["details"]

    # 404 -> not_found
    with patch("src.web.cross_platform._fetch", return_value=(404, b'{}', {}, "HTTP 404")):
        res = _check_github("nonexistent_user_9999")
        assert res["status"] == "not_found"
        assert res["exists"] is False

    # 403 / 429 -> error (rate limit)
    with patch("src.web.cross_platform._fetch", return_value=(403, b'{"message": "rate limit"}', {}, "HTTP 403")):
        res = _check_github("octocat")
        assert res["status"] == "error"
        assert res["exists"] is False
        assert "Rate limit" in res["details"]

    # 0 -> error (timeout or network error)
    with patch("src.web.cross_platform._fetch", return_value=(0, b'', {}, "Connection timed out")):
        res = _check_github("octocat")
        assert res["status"] == "error"
        assert res["exists"] is False
        assert "timeout" in res["details"].lower()


def test_service_search_cross_platform(make_service):
    svc = make_service("target_dev")
    with patch("src.web.cross_platform.scan_cross_platform") as mock_scan:
        mock_scan.return_value = {"target": "target_dev", "found_count": 0, "platforms": []}
        res = svc.search_cross_platform()
        assert res["target"] == "target_dev"
        mock_scan.assert_called_once_with("target_dev")


def test_service_get_tagged_posts(make_service):
    tagged_items = [
        {
            "id": "1001",
            "pk": 1001,
            "user": {"pk": "201", "username": "friend_bob", "full_name": "Bob Friend", "is_verified": False},
            "caption": {"text": "Chilling with @target_user at the beach"},
            "taken_at": 1700000000,
            "media_type": 1,
            "image_versions2": {
                "candidates": [
                    {"url": "https://cdn.test/thumb.jpg", "width": 150, "height": 150},
                    {"url": "https://cdn.test/high_res.jpg", "width": 1080, "height": 1080},
                ]
            },
            "location": {"name": "Bondi Beach", "address": "Sydney", "lat": -33.89, "lng": 151.27},
            "like_count": 42,
            "comment_count": 5,
            "usertags": {
                "in": [
                    {"user": {"pk": "1", "username": "target_user"}},
                    {"user": {"pk": "301", "username": "co_friend_charlie", "full_name": "Charlie"}},
                ]
            },
        }
    ]

    class FakeTaggedApi:
        def user_by_username_v2(self, username):
            return {"user": {"pk": "1", "username": username, "is_private": False}}

        def user_tag_medias_v2(self, user_id, page_id=None, **k):
            return {"response": {"items": tagged_items}, "next_page_id": None}

    svc = OsintgramService("target_user", FakeTaggedApi())
    posts = svc.get_tagged_posts(limit=10)
    assert len(posts) == 1
    p = posts[0]
    assert p["id"] == "1001"
    assert p["author"]["username"] == "friend_bob"
    assert p["caption"] == "Chilling with @target_user at the beach"
    assert p["location"]["name"] == "Bondi Beach"
    assert p["like_count"] == 42
    assert p["comment_count"] == 5
    # co_tagged should exclude target_user and include co_friend_charlie
    assert len(p["co_tagged"]) == 1
    assert p["co_tagged"][0]["username"] == "co_friend_charlie"
