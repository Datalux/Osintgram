"""Shared fixtures for the test suite.

Everything here is synthetic - no real Instagram/personal data - and shaped
like HikerAPI's current ("g2") responses so the tests exercise the same
parsing the live backend goes through. A FakeHiker stands in for the network:
no HikerAPI token, quota, or connectivity is ever needed to run the tests.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Never let a test touch the on-disk request cache (or a real credentials file).
os.environ["HIKER_CACHE_PATH"] = ""


def _img(width=720):
    return {"image_versions2": {"candidates": [{"url": f"https://cdn.test/{width}.jpg", "width": width}]}}


def photo(pk, *, alt=None, likes=10, comments=2, taken_at=1_700_000_000, code=None, usertags=None):
    """A g2-shaped single photo post (typed field names, no `pk` on users)."""
    return {
        "id": f"{pk}_1",
        "pk": str(pk),
        "code": code or f"C{pk}",
        "media_type": 1,
        "product_type": "feed",
        "like_count": likes,
        "comment_count": comments,
        "1ltaken_at": taken_at,
        "accessibility_caption": alt,
        "caption": {"text": f"caption {pk} #travel"},
        "usertags": usertags,
        **_img(),
    }


def video(pk, *, plays=1000, song=None, coauthor=None, paid=False, taken_at=1_700_100_000):
    post = {
        "id": f"{pk}_1",
        "pk": str(pk),
        "code": f"R{pk}",
        "media_type": 2,
        "product_type": "clips",
        "like_count": 5,
        "comment_count": 1,
        "play_count": plays,
        "1ltaken_at": taken_at,
        "is_paid_partnership": paid,
        "video_versions": [{"url": f"https://cdn.test/{pk}.mp4"}],
        **_img(),
    }
    if coauthor:
        post["coauthor_producers"] = [{"id": "99", "username": coauthor, "full_name": "Co Author"}]
    if song:
        post["clips_metadata"] = {"music_info": {"music_asset_info": {"title": song, "display_artist": "Artist"}}}
    return post


def carousel(pk, media_types=(1, 2, 1), taken_at=1_700_200_000):
    children = []
    for i, mt in enumerate(media_types):
        child = {"id": f"{pk}_{i}", "media_type": mt, "accessibility_caption": f"alt {pk}.{i}" if mt == 1 else None, **_img()}
        if mt == 2:
            child["video_versions"] = [{"url": f"https://cdn.test/{pk}_{i}.mp4"}]
        children.append(child)
    return {
        "id": f"{pk}_c",
        "pk": str(pk),
        "code": f"K{pk}",
        "media_type": 8,
        "product_type": "carousel_container",
        "like_count": 20,
        "comment_count": 3,
        "1ltaken_at": taken_at,
        "carousel_media": children,
        **_img(),
    }


def user(pk, name):
    # g2 user objects have "id" but no "pk" - normalize_payload derives it.
    return {"id": str(pk), "username": name, "full_name": name.title(), "is_private": False, "is_verified": False}


def _page(items, key, cursor):
    return {"response": {key: items}, "next_page_id": cursor}


class FakeHiker:
    """A HikerAPI-shaped client backed by in-memory fixtures. Counts calls so
    tests can assert on request cost; ``feed``/``followers``/``following`` may
    be several pages (a list of lists)."""

    def __init__(self, *, users=None, feed=None, followers=None, following=None,
                 stories=None, highlights=None, suggested=None, about=None, private=False):
        self.users = users or {}
        self.feed_pages = feed if feed and isinstance(feed[0], list) else [feed or []]
        self.follower_pages = followers if followers and isinstance(followers[0], list) else [followers or []]
        self.following_pages = following if following and isinstance(following[0], list) else [following or []]
        self.stories = stories or []
        self.highlights = highlights or []
        self.suggested = suggested or []
        self.about = about
        self.private = private
        self.calls = []

    def _by_id(self, pages, cursor):
        idx = int(cursor) if cursor else 0
        nxt = str(idx + 1) if idx + 1 < len(pages) else None
        return pages[idx] if idx < len(pages) else [], nxt

    def user_by_username_v2(self, username, **k):
        self.calls.append(("user_by_username_v2", username))
        u = self.users.get(username)
        if u is None:
            return {"detail": "not found"}
        return {"user": {"pk": u["pk"], "username": username, "is_private": u.get("private", False),
                         "full_name": u.get("full_name", username), **u.get("extra", {})}}

    def user_by_id_v2(self, pk, **k):
        self.calls.append(("user_by_id_v2", pk))
        return {"user": self.users.get(str(pk), {}).get("detail", {})}

    def user_medias_g2(self, user_id, next_page_id=None, **k):
        self.calls.append(("user_medias_g2", user_id, next_page_id))
        items, nxt = self._by_id(self.feed_pages, next_page_id)
        return _page(items, "items", nxt)

    def user_followers_g2(self, user_id, page_id=None, **k):
        self.calls.append(("user_followers_g2", user_id, page_id))
        items, nxt = self._by_id(self.follower_pages, page_id)
        return _page(items, "users", nxt)

    def user_following_g2(self, user_id, page_id=None, **k):
        self.calls.append(("user_following_g2", user_id, page_id))
        items, nxt = self._by_id(self.following_pages, page_id)
        return _page(items, "users", nxt)

    def user_stories_v2(self, user_id, **k):
        self.calls.append(("user_stories_v2", user_id))
        return {"reel": {"items": self.stories}}

    def user_highlights_v2(self, user_id, **k):
        self.calls.append(("user_highlights_v2", user_id))
        return {"response": {"tray": self.highlights}}

    def user_suggested_profiles_v2(self, user_id, **k):
        self.calls.append(("user_suggested_profiles_v2", user_id))
        return {"users": self.suggested}

    def user_about_gql(self, user_id, **k):
        self.calls.append(("user_about_gql", user_id))
        return self.about or {}


@pytest.fixture
def make_service():
    from src.osint_service import OsintgramService

    def _make(target="target", **kwargs):
        users = kwargs.setdefault("users", {})
        users.setdefault(target, {"pk": 100, "private": kwargs.pop("private", False)})
        return OsintgramService(target, FakeHiker(**kwargs))

    return _make
