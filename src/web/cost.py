"""Estimate how many backend requests a set of commands will cost.

HikerAPI bills per request, so the useful question before pressing "Esegui"
is "how much will this spend?". Every estimate here is derived from the same
pagination rules the capabilities in src/osint_service.py actually use, plus
the target's own counters (posts/followers/following), which the profile
lookup already provides - so estimating costs one profile request that the
run itself would spend anyway (and which the request cache then serves).

Estimates are ranges, never promises: page sizes vary with the endpoint and
Instagram's own batching, and a cache hit costs nothing at all.
"""
import math
from typing import Optional

# Observed page sizes (items per request) for the endpoints behind each
# capability - low/high, so the estimate comes out as a range.
POSTS_PER_PAGE = (9, 12)
USERS_PER_PAGE = (25, 50)
COMMENTS_PER_PAGE = (15, 20)

# Capabilities that only read the already-fetched profile object.
_FREE = {"get_user_info", "get_user_propic"}
# HikerAPI bills these at a flat rate per call (its docs say 2 per call for
# the story/highlight endpoints).
_FLAT = {"get_user_stories": 2, "get_highlights": 2, "get_suggested_profiles": 1, "get_account_about": 1}
# Capabilities that page through the target's feed.
_FEED = {
    "get_hashtags", "get_addrs", "get_captions", "get_total_comments", "get_total_likes",
    "get_media_type", "get_posting_times", "get_photo_descriptions", "get_user_photos",
    "get_people_tagged_by_user",
}
# Feed + one comment scan per post.
_FEED_AND_COMMENTS = {"get_comment_data", "get_people_who_commented"}
_CONTACTS = {"get_followers_email", "get_followings_email", "get_followers_phone", "get_followings_phone"}


def _pages(count: Optional[int], per_page: tuple) -> tuple:
    """Requests needed to page through `count` items (low, high)."""
    if not count:
        return (0, 0)
    high, low = per_page  # fewer items per page => more requests
    return (math.ceil(count / low), math.ceil(count / high))


def _capped(limit, total, fallback=200):
    """How many items will actually be fetched: the user's limit, the profile's
    own total, or a guess when neither is known."""
    known = [n for n in (limit, total) if isinstance(n, int) and n > 0]
    return min(known) if known else fallback


def estimate_command(name: str, params: dict, profile: dict, max_items: Optional[int] = None) -> tuple:
    """(low, high) requests for one command. Unknown commands count as 1."""
    params = params or {}
    posts_total = profile.get("media_count")
    followers_total = profile.get("follower_count")
    following_total = profile.get("following_count")

    def feed_pages(extra_cap=None):
        limit = params.get("limit_posts", params.get("limit"))
        if max_items is not None:
            limit = max_items if limit is None else min(limit, max_items)
        return _pages(_capped(limit, extra_cap if extra_cap is not None else posts_total), POSTS_PER_PAGE)

    if name in _FREE:
        return (0, 0)
    if name in _FLAT:
        return (_FLAT[name], _FLAT[name])
    if name in _FEED:
        return feed_pages()
    if name in _FEED_AND_COMMENTS:
        low, high = feed_pages()
        posts = _capped(params.get("limit_posts"), posts_total)
        # At least one comments request per post, more when a post has many.
        return (low + posts, high + posts * 2)
    if name in {"get_followers", "get_followings"}:
        total = followers_total if name == "get_followers" else following_total
        limit = params.get("limit")
        if max_items is not None:
            limit = max_items if limit is None else min(limit, max_items)
        return _pages(_capped(limit, total), USERS_PER_PAGE)
    if name == "get_people_who_tagged":
        return _pages(_capped(params.get("limit"), None, fallback=100), POSTS_PER_PAGE)
    if name in _CONTACTS:
        total = followers_total if "followers" in name else following_total
        checks = _capped(params.get("max_checks"), total, fallback=100)
        if max_items is not None:
            checks = min(checks, max_items)
        pages = _pages(checks, USERS_PER_PAGE)
        # One profile lookup per candidate examined, on top of the list pages.
        return (pages[0] + checks, pages[1] + checks)
    if name == "search_hashtag":
        # ~24 posts per hashtag page.
        return _pages(_capped(params.get("limit"), None, fallback=30), (20, 24))
    if name == "search_location":
        pages = _pages(_capped(params.get("limit"), None, fallback=30), USERS_PER_PAGE)
        return (pages[0] + 1, pages[1] + 1)  # plus the place lookup
    if name == "compare_with":
        scope = params.get("scope") or "both"
        limit = params.get("limit")
        low = high = 1  # resolving the other account
        if scope in ("followers", "both"):
            for total in (followers_total, None):
                p = _pages(_capped(limit, total), USERS_PER_PAGE)
                low, high = low + p[0], high + p[1]
        if scope in ("followings", "both"):
            for total in (following_total, None):
                p = _pages(_capped(limit, total), USERS_PER_PAGE)
                low, high = low + p[0], high + p[1]
        return (low, high)
    return (1, 1)


def estimate(calls: list, profile: dict, max_items: Optional[int] = None) -> dict:
    """Per-command and total estimates for a whole run."""
    per_command = []
    total_low = total_high = 0
    for call in calls:
        low, high = estimate_command(call["name"], call.get("args") or {}, profile, max_items)
        per_command.append({"name": call["name"], "low": low, "high": high})
        total_low += low
        total_high += high
    if max_items is not None:
        # "Limite chiamate" is a hard ceiling on the whole run.
        total_low = min(total_low, max_items)
        total_high = min(total_high, max_items)
    return {"per_command": per_command, "total_low": total_low, "total_high": total_high}
