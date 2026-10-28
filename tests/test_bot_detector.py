"""Tests for the Bot and Anomaly Detector (audit_followers)."""
import pytest
from src.web.bot_detector import (
    _calculate_entropy,
    audit_followers_list,
    evaluate_follower_risk,
)
from tests.conftest import user


def test_calculate_entropy():
    assert _calculate_entropy("") == 0.0
    assert _calculate_entropy("aaaa") == 0.0
    # Random-like strings should have higher entropy than repetitive ones
    assert _calculate_entropy("abcdefgh") > _calculate_entropy("aabbccdd")


def test_evaluate_follower_verified_is_zero_risk():
    u = {
        "id": "1",
        "username": "verified_vip",
        "full_name": "VIP Person",
        "is_verified": True,
        "has_anonymous_profile_picture": True,
    }
    score, reasons = evaluate_follower_risk(u)
    assert score == 0
    assert reasons == []


def test_evaluate_follower_healthy_account():
    u = {
        "id": "2",
        "username": "alice_walker",
        "full_name": "Alice Walker",
        "is_verified": False,
        "has_anonymous_profile_picture": False,
        "profile_pic_url": "https://cdn.instagram.com/pic_custom.jpg",
    }
    score, reasons = evaluate_follower_risk(u)
    assert score < 20
    assert reasons == []


def test_evaluate_follower_missing_avatar():
    u = {
        "id": "3",
        "username": "john_doe",
        "full_name": "John Doe",
        "is_verified": False,
        "has_anonymous_profile_picture": True,
    }
    score, reasons = evaluate_follower_risk(u)
    assert score >= 25
    assert any("profile picture" in r.lower() for r in reasons)


def test_evaluate_follower_trailing_digits():
    u = {
        "id": "4",
        "username": "jessica984182",
        "full_name": "Jessica",
        "is_verified": False,
    }
    score, reasons = evaluate_follower_risk(u)
    assert score >= 25
    assert any("trailing digits" in r.lower() for r in reasons)


def test_evaluate_follower_spam_keywords():
    u = {
        "id": "5",
        "username": "crypto_forex_trader",
        "full_name": "DM For Promo & Bitcoin",
        "is_verified": False,
    }
    score, reasons = evaluate_follower_risk(u)
    assert score >= 25
    assert any("spam" in r.lower() for r in reasons)


def test_evaluate_follower_high_risk_bot():
    u = {
        "id": "6",
        "username": "bot_98419284",
        "full_name": "",
        "is_verified": False,
        "has_anonymous_profile_picture": True,
    }
    score, reasons = evaluate_follower_risk(u)
    assert score >= 70
    assert len(reasons) >= 3


def test_audit_followers_list_empty():
    res = audit_followers_list([])
    assert res["total_analyzed"] == 0
    assert res["authenticity_score"] == 100.0
    assert res["flagged_accounts"] == []


def test_audit_followers_list_mixed_cohort():
    followers = [
        # Clean organic
        {"id": "1", "username": "clara", "full_name": "Clara", "is_verified": False, "has_anonymous_profile_picture": False},
        {"id": "2", "username": "verified_star", "full_name": "Star", "is_verified": True},
        # Definite bot
        {"id": "3", "username": "bot_9948281", "full_name": "", "is_verified": False, "has_anonymous_profile_picture": True},
        # Spam
        {"id": "4", "username": "crypto_gains", "full_name": "Forex Promo", "is_verified": False},
    ]
    res = audit_followers_list(followers)
    assert res["total_analyzed"] == 4
    assert res["metrics"]["verified_count"] == 1
    assert res["metrics"]["bot_count"] >= 1
    assert res["authenticity_score"] < 100.0
    assert len(res["flagged_accounts"]) >= 2
    # Verify sorted by risk_score desc
    scores = [a["risk_score"] for a in res["flagged_accounts"]]
    assert scores == sorted(scores, reverse=True)


def test_service_audit_followers(make_service):
    followers = [
        user(1, "alice"),
        user(2, "bob8491823"),
    ]
    svc = make_service(followers=followers)
    result = svc.audit_followers(limit=10)
    assert result["total_analyzed"] == 2
    assert "authenticity_score" in result
    assert "metrics" in result
    assert "flagged_accounts" in result
