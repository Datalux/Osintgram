"""Adapter exposing a HikerAPI-shaped client interface backed by instagrapi.

OsintgramService (src/osint_service.py) only ever calls a dozen methods on the
client it's given (user_by_username_v2, user_medias_g2, media_comments_v2,
user_followers_g2, user_following_g2, user_tag_medias_v2, user_stories_v2,
user_by_id_v2, user_highlights_v2, hashtag_medias_top_v2 /
hashtag_medias_recent_v2, fbsearch_places_v2, location_medias_recent_chunk_v1)
- always returning the same shapes HikerAPI does ({"response": {"items"|
"users"|"comments": [...]}, "next_page_id": ...} or {"user": {...}}, with
next_page_id falsy once pagination is exhausted). InstagrapiClient implements
those same methods on top of instagrapi, so OsintgramService needs zero
changes to run on either backend. The one exception is
user_suggested_profiles_v2, which has no instagrapi equivalent at all and
says so instead of pretending.

Login only ever loads a previously saved session (see scripts/instagrapi_login.py)
and never performs an interactive login itself - a 2FA/challenge prompt can't
be answered from inside a web request. Run the setup script once first.
"""
import configparser
import os
from pathlib import Path
from typing import Optional

# Imported lazily inside __init__, not here: instagrapi is an optional
# dependency (the HikerAPI backend is the default one) and importing this
# module - for DEFAULT_SESSION_PATH, or to test the translation layer below
# against a stand-in client - must not require having it installed.
DEFAULT_SESSION_PATH = "config/instagrapi_session.json"


class InstagrapiBackendError(Exception):
    """Raised when the instagrapi backend can't authenticate."""


def resolve_instagrapi_credentials(
    credentials_path: str = "config/credentials.ini",
) -> tuple[Optional[str], Optional[str]]:
    """Resolve (username, password) the same way resolve_hiker_token resolves
    its token - env vars first, then config/credentials.ini, never raising.
    Reuses the [Credentials] username/password fields already used by the
    same config file the HikerAPI token lives in, rather than inventing new
    config surface.
    """
    username = os.getenv("INSTAGRAM_USERNAME")
    password = os.getenv("INSTAGRAM_PASSWORD")
    if username and password:
        return username, password
    try:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(credentials_path)
        username = username or parser.get("Credentials", "username", fallback=None) or None
        password = password or parser.get("Credentials", "password", fallback=None) or None
    except Exception:
        pass
    return username, password


def session_exists(session_path: str = DEFAULT_SESSION_PATH) -> bool:
    return Path(session_path).exists()


class InstagrapiClient:
    """HikerAPI-shaped wrapper around an authenticated instagrapi.Client."""

    def __init__(self, username: str, password: str, session_path: str = DEFAULT_SESSION_PATH):
        session_file = Path(session_path)
        if not session_file.exists():
            raise InstagrapiBackendError(
                f"No saved instagrapi session at {session_path}. Run "
                "`python scripts/instagrapi_login.py` once from a terminal to "
                "log in (and resolve any 2FA/challenge prompt) before using "
                "this backend."
            )

        from instagrapi import Client

        self._cl = Client()
        self._cl.load_settings(session_file)
        try:
            self._cl.login(username, password)
        except Exception as e:
            raise InstagrapiBackendError(
                f"instagrapi login failed using the saved session: {e}. "
                "Re-run `python scripts/instagrapi_login.py` to refresh it."
            ) from e

    # ---- shape-translation helpers ----

    @staticmethod
    def _full_user_to_dict(user) -> dict:
        d = {
            "pk": user.pk,
            "username": user.username,
            "full_name": user.full_name,
            "is_private": user.is_private,
            "is_verified": user.is_verified,
            "biography": getattr(user, "biography", None),
            "follower_count": getattr(user, "follower_count", None),
            "following_count": getattr(user, "following_count", None),
            "media_count": getattr(user, "media_count", None),
            "is_business": getattr(user, "is_business", None),
            "public_email": getattr(user, "public_email", None),
            "contact_phone_number": getattr(user, "contact_phone_number", None),
            "city_name": getattr(user, "city_name", None),
            "address_street": getattr(user, "address_street", None),
            "category": getattr(user, "category", None),
        }
        # The rest of what instagrapi's UserFull carries, so get_user_info
        # shows the same fields on either backend (see _EXTRA_PROFILE_FIELDS).
        for field in ("external_url", "account_type", "category_name", "business_category_name",
                      "business_contact_method", "public_phone_country_code", "public_phone_number",
                      "zip", "latitude", "longitude", "instagram_location_id"):
            value = getattr(user, field, None)
            if value not in (None, ""):
                d[field] = str(value) if field == "external_url" else value
        pic_hd = getattr(user, "profile_pic_url_hd", None)
        if pic_hd:
            d["hd_profile_pic_url_info"] = {"url": str(pic_hd)}
        return d

    @staticmethod
    def _short_user_to_dict(user) -> dict:
        return {
            "pk": user.pk,
            "username": user.username,
            "full_name": user.full_name,
            "is_private": user.is_private,
            "is_verified": user.is_verified,
        }

    @staticmethod
    def _media_to_dict(media) -> dict:
        d = {
            "id": media.id,
            "code": media.code,
            "product_type": media.product_type,
            "comment_count": media.comment_count or 0,
            "like_count": media.like_count or 0,
            "media_type": media.media_type,
            "accessibility_caption": getattr(media, "accessibility_caption", None),
            "caption": {"text": media.caption_text} if media.caption_text else None,
            "taken_at": int(media.taken_at.timestamp()) if media.taken_at else None,
            # Who posted it: irrelevant for a target's own feed, essential for
            # the hashtag/place searches, where every post has a different author.
            "user": InstagrapiClient._short_user_to_dict(media.user) if media.user else {},
            "usertags": [
                {
                    "user": {
                        "pk": tag.user.pk,
                        "username": tag.user.username,
                        "full_name": tag.user.full_name,
                    }
                }
                for tag in (media.usertags or [])
                if tag.user
            ],
        }
        if media.location and media.location.lat is not None and media.location.lng is not None:
            d["location"] = {"lat": media.location.lat, "lng": media.location.lng}

        if media.media_type == 8 and media.resources:
            # Album/carousel: each resource is its own photo or video.
            d["carousel_media"] = []
            for resource in media.resources:
                item = {
                    "id": resource.pk,
                    "media_type": resource.media_type,
                    "accessibility_caption": getattr(resource, "accessibility_caption", None),
                }
                if resource.thumbnail_url:
                    item["image_versions2"] = {"candidates": [{"url": str(resource.thumbnail_url)}]}
                if resource.media_type == 2 and resource.video_url:
                    item["video_versions"] = [{"url": str(resource.video_url)}]
                d["carousel_media"].append(item)
        else:
            # Single photo or video post: image_versions2 holds the main
            # image (or, for a video, its thumbnail/cover).
            candidates = []
            if media.image_versions2 and media.image_versions2.candidates:
                candidates = [{"url": str(c.url)} for c in media.image_versions2.candidates]
            elif media.thumbnail_url:
                candidates = [{"url": str(media.thumbnail_url)}]
            if candidates:
                d["image_versions2"] = {"candidates": candidates}
            if media.media_type == 2 and media.video_url:
                d["video_versions"] = [{"url": str(media.video_url)}]
        return d

    @staticmethod
    def _comment_to_dict(comment) -> dict:
        user = comment.user
        return {
            "user_id": user.pk if user else None,
            "user": {"pk": user.pk, "username": user.username, "full_name": user.full_name} if user else {},
            "text": comment.text,
        }

    @staticmethod
    def _story_to_dict(story) -> dict:
        d = {"id": story.id, "media_type": story.media_type}
        # Set for videos too (their cover frame), like HikerAPI's raw items.
        if story.thumbnail_url:
            d["image_versions2"] = {"candidates": [{"url": str(story.thumbnail_url)}]}
        if story.media_type == 2 and story.video_url:
            d["video_versions"] = [{"url": str(story.video_url)}]
        return d

    # ---- HikerAPI-shaped methods used by OsintgramService ----

    def user_by_username_v2(self, username: str) -> dict:
        try:
            user = self._cl.user_info_by_username_v1(username)
        except Exception as e:
            if "not found" in str(e).lower() or type(e).__name__ == "UserNotFound":
                return {"detail": str(e)}
            return {"error": str(e)}
        return {"user": self._full_user_to_dict(user)}

    def user_by_id_v2(self, pk) -> dict:
        try:
            user = self._cl.user_info_v1(str(pk))
        except Exception as e:
            return {"error": str(e)}
        return {"user": self._full_user_to_dict(user)}

    def user_medias_g2(self, user_id, next_page_id: Optional[str] = None) -> dict:
        medias, cursor = self._cl.user_medias_paginated_v1(str(user_id), amount=33, end_cursor=next_page_id or "")
        return {
            "response": {"items": [self._media_to_dict(m) for m in medias]},
            "next_page_id": cursor or None,
        }

    def media_comments_v2(self, media_id, page_id: str = "") -> dict:
        try:
            comments, cursor = self._cl.media_comments_chunk(str(media_id), max_amount=20, min_id=page_id or None)
        except Exception as e:
            if type(e).__name__ == "MediaNotFound":
                raise RuntimeError(f"Entries not found: {e}") from e
            raise
        return {
            "response": {"comments": [self._comment_to_dict(c) for c in comments]},
            "next_page_id": cursor or None,
        }

    def user_followers_g2(self, user_id, page_id: Optional[str] = None) -> dict:
        users, cursor = self._cl.user_followers_v1_chunk(str(user_id), max_amount=50, max_id=page_id or "")
        return {
            "response": {"users": [self._short_user_to_dict(u) for u in users]},
            "next_page_id": cursor or None,
        }

    def user_following_g2(self, user_id, page_id: Optional[str] = None) -> dict:
        users, cursor = self._cl.user_following_v1_chunk(str(user_id), max_amount=50, max_id=page_id or "")
        return {
            "response": {"users": [self._short_user_to_dict(u) for u in users]},
            "next_page_id": cursor or None,
        }

    def user_tag_medias_v2(self, user_id, page_id: str = "") -> dict:
        medias, cursor = self._cl.usertag_medias_paginated_v1(str(user_id), amount=33, end_cursor=page_id or "")
        return {
            "response": {"items": [self._media_to_dict(m) for m in medias]},
            "next_page_id": cursor or None,
        }

    def user_stories_v2(self, user_id) -> dict:
        stories = self._cl.user_stories_v1(str(user_id))
        return {"reel": {"items": [self._story_to_dict(s) for s in stories]}}

    def user_highlights_v2(self, user_id, **kwargs) -> dict:
        tray = []
        for h in self._cl.user_highlights(str(user_id)):
            cover = getattr(h, "cover_media", None)
            url = getattr(getattr(cover, "cropped_image_version", None), "url", None) if cover else None
            tray.append({
                "id": f"highlight:{h.pk}",
                "title": h.title,
                "media_count": h.media_count,
                "cover_media": {"cropped_image_version": {"url": str(url)} if url else {}},
                "created_at": None,
                "latest_reel_media": None,
            })
        return {"response": {"tray": tray}}

    # ---- hashtag / place search ----
    #
    # instagrapi's chunked variants (hashtag_medias_v1_chunk,
    # location_medias_v1_chunk) are what make paging possible, but they came
    # late and not every installed version has them - hence the getattr probe
    # and the one-shot fallback, which simply returns everything at once and
    # no cursor. Either way the caller (OsintgramService.search_*) sees the
    # same shape and just stops when there's no next page.

    def _hashtag_chunk(self, name: str, tab_key: str, page_id) -> dict:
        chunked = getattr(self._cl, "hashtag_medias_v1_chunk", None)
        if chunked is not None:
            medias, cursor = chunked(name, max_amount=30, tab_key=tab_key, max_id=page_id or None)
        else:
            one_shot = getattr(self._cl, f"hashtag_medias_{tab_key}_v1")
            medias = one_shot(name, amount=30) if not page_id else []
            cursor = None
        return {
            "response": {"items": [self._media_to_dict(m) for m in medias]},
            "next_page_id": cursor or None,
        }

    def hashtag_medias_top_v2(self, name: str, page_id=None, **kwargs) -> dict:
        return self._hashtag_chunk(name, "top", page_id)

    def hashtag_medias_recent_v2(self, name: str, page_id=None, **kwargs) -> dict:
        return self._hashtag_chunk(name, "recent", page_id)

    def fbsearch_places_v2(self, query: str, **kwargs) -> dict:
        places = self._cl.fbsearch_places(query)
        return {"items": [{"location": {
            "pk": location.pk,
            "name": location.name,
            "address": location.address,
            "city": location.city,
            "lat": location.lat,
            "lng": location.lng,
        }} for location in places if location.pk]}

    def location_medias_recent_chunk_v1(self, location_pk, max_id=None, **kwargs) -> list:
        """Answers [medias, next_max_id] - the shape HikerAPI uses here."""
        chunked = getattr(self._cl, "location_medias_v1_chunk", None)
        if chunked is not None:
            medias, cursor = chunked(int(location_pk), max_amount=30, tab_key="recent", max_id=max_id or None)
        else:
            medias = self._cl.location_medias_recent_v1(int(location_pk), amount=30) if not max_id else []
            cursor = None
        return [[self._media_to_dict(m) for m in medias], cursor or None]

    def user_suggested_profiles_v2(self, user_id, **kwargs) -> dict:
        # instagrapi has no equivalent of Instagram's suggestion chaining.
        from src.osint_service import OsintServiceError

        raise OsintServiceError("Suggested profiles are not available on the instagrapi backend (HikerAPI only).")

    def user_about_gql(self, user_id, **kwargs) -> dict:
        # instagrapi exposes no "About this account" query.
        from src.osint_service import OsintServiceError

        raise OsintServiceError(
            "\"About this account\" is not available on the instagrapi backend (HikerAPI only).")
