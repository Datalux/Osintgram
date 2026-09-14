"""Tests for the request-cost estimator (src/web/cost.py)."""
from src.web import cost

PROFILE = {"media_count": 120, "follower_count": 1500, "following_count": 300}


def est(name, args=None, max_items=None):
    return cost.estimate_command(name, args or {}, PROFILE, max_items)


def test_profile_only_commands_are_free():
    # The profile is already fetched when the target is resolved.
    assert est("get_user_info") == (0, 0)
    assert est("get_user_propic") == (0, 0)


def test_flat_rate_commands():
    assert est("get_user_stories") == (2, 2)  # HikerAPI bills 2 per call
    assert est("get_suggested_profiles") == (1, 1)


def test_feed_commands_scale_with_post_count():
    low, high = est("get_media_type")
    assert 0 < low <= high  # 120 posts over ~9-12 per page
    # A smaller limit_posts must cost less.
    assert est("get_media_type", {"limit_posts": 20})[1] < high


def test_followers_scale_with_limit_and_total():
    assert est("get_followers", {"limit": 100})[1] <= est("get_followers", {"limit": 1000})[1]
    # Never more than the account actually has.
    capped = est("get_followings", {"limit": 10_000})
    assert capped == est("get_followings", {"limit": 300})


def test_contact_scan_costs_one_request_per_candidate():
    low, high = est("get_followers_email", {"max_checks": 50})
    assert low >= 50  # one profile lookup each, plus the list pages


def test_comment_commands_cost_more_than_plain_feed():
    assert est("get_comment_data", {"limit_posts": 10})[0] > est("get_captions", {"limit_posts": 10})[0]


def test_compare_scope_halves_the_cost():
    both = est("compare_with", {"scope": "both", "limit": 500})
    one_side = est("compare_with", {"scope": "followers", "limit": 500})
    assert one_side[1] < both[1]


def test_unknown_command_counts_as_one():
    assert est("get_something_new") == (1, 1)


def test_total_is_capped_by_the_call_limit():
    calls = [{"name": "get_followers_email", "args": {"max_checks": 100}}]
    assert cost.estimate(calls, PROFILE)["total_high"] > 50
    assert cost.estimate(calls, PROFILE, max_items=50)["total_high"] == 50


def test_estimate_lists_every_command():
    calls = [{"name": "get_user_info", "args": {}}, {"name": "get_followers", "args": {"limit": 50}}]
    result = cost.estimate(calls, PROFILE)
    assert [c["name"] for c in result["per_command"]] == ["get_user_info", "get_followers"]
    assert result["total_high"] == sum(c["high"] for c in result["per_command"])
