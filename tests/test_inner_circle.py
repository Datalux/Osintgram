"""Unit tests for the Inner Circle interaction affinity algorithm."""
from unittest.mock import MagicMock

import pytest

from src.inner_circle import (
    InnerCircleAnalyzer,
    WEIGHT_CAPTION_MENTION,
    WEIGHT_COMMENT,
    WEIGHT_MUTUAL_FOLLOW,
    WEIGHT_TAGGED_POST,
)
from src.osint_service import OsintgramService, PrivateProfileError
from src.web.tools import build_tools, tool_specs


def test_inner_circle_analyzer_ranking_and_tiers():
    analyzer = InnerCircleAnalyzer("target_alice")

    posts = [
        {
            "id": "post_1",
            "usertags": {"in": [{"user": {"username": "bestie_bob", "full_name": "Bob B"}}]},
            "caption": {"text": "Chilling with @bestie_bob and @acquaintance_charlie!"},
        },
        {
            "id": "post_2",
            "usertags": {"in": [{"user": {"username": "bestie_bob"}}]},
            "caption": "Throwback with @bestie_bob",
        },
    ]

    comments_by_post = {
        "post_1": [
            {"user": {"username": "bestie_bob"}, "text": "Best weekend ever!"},
            {"user": {"username": "commenter_dan"}, "text": "Nice photo"},
        ],
        "post_2": [
            {"user": {"username": "bestie_bob"}, "text": "Take me back!"},
        ],
    }

    # Mutual follow with bestie_bob
    followers = [{"username": "bestie_bob"}, {"username": "commenter_dan"}]
    following = [{"username": "bestie_bob"}, {"username": "acquaintance_charlie"}]

    results = analyzer.analyze(
        posts=posts,
        comments_by_post=comments_by_post,
        followers=followers,
        following=following,
        limit=10,
    )

    assert len(results) >= 3

    # bestie_bob should be rank #1 with high score
    bob = results[0]
    assert bob["username"] == "bestie_bob"
    assert bob["is_mutual"] is True
    assert bob["tagged_count"] == 2
    assert bob["comments_count"] == 2
    assert bob["mentions_count"] == 2

    expected_bob_score = (
        WEIGHT_MUTUAL_FOLLOW
        + (2 * WEIGHT_TAGGED_POST)
        + (2 * WEIGHT_COMMENT)
        + (2 * WEIGHT_CAPTION_MENTION)
    )
    assert bob["score"] == round(expected_bob_score, 1)
    assert bob["tier"] == "Core Confidant"

    # Target itself should never be included
    assert all(r["username"] != "target_alice" for r in results)


def test_inner_circle_service_integration():
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {
        "user": {"pk": "100", "username": "alice", "is_private": False}
    }
    mock_api.user_medias_g2.return_value = {
        "response": {
            "items": [
                {
                    "id": "m1",
                    "pk": "m1",
                    "caption": {"text": "Hanging with @charlie"},
                    "usertags": {"in": [{"user": {"username": "bob", "pk": "200"}}]},
                }
            ]
        },
        "next_page_id": None,
    }
    mock_api.media_comments_v2.return_value = {
        "response": {"comments": [{"user": {"username": "bob", "pk": "200"}, "text": "Love it!"}]},
        "next_page_id": None,
    }
    mock_api.user_followers_g2.return_value = {
        "response": {"users": [{"pk": "200", "username": "bob"}]},
        "next_page_id": None,
    }
    mock_api.user_following_g2.return_value = {
        "response": {"users": [{"pk": "200", "username": "bob"}]},
        "next_page_id": None,
    }

    service = OsintgramService("alice", mock_api)
    circle = service.get_inner_circle(limit=5, scan_posts=1)

    assert len(circle) == 2  # bob and charlie
    assert circle[0]["username"] == "bob"
    assert circle[0]["is_mutual"] is True
    assert circle[0]["tagged_count"] == 1
    assert circle[0]["comments_count"] == 1

    assert circle[1]["username"] == "charlie"
    assert circle[1]["mentions_count"] == 1


def test_inner_circle_private_profile_guard():
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {
        "user": {"pk": "100", "username": "alice", "is_private": True}
    }
    service = OsintgramService("alice", mock_api)
    with pytest.raises(PrivateProfileError):
        service.get_inner_circle()


def test_inner_circle_tool_registered():
    specs = tool_specs()
    inner_spec = next((s for s in specs if s["name"] == "get_inner_circle"), None)
    assert inner_spec is not None
    assert any(p["name"] == "limit" for p in inner_spec["params"])
    assert any(p["name"] == "scan_posts" for p in inner_spec["params"])

    mock_service = MagicMock()
    mock_service.get_inner_circle.return_value = [{"username": "bob", "score": 10.0}]
    tools = build_tools(mock_service)
    tool_fn = next((t for t in tools if t.__name__ == "get_inner_circle"), None)
    assert tool_fn is not None
    res = tool_fn(limit=5)
    assert "bob" in res
