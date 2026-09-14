"""Side-effect-free OSINT service layer over HikerAPI.

Every method returns a plain, JSON-serializable Python structure instead of
printing to stdout, writing files, or blocking on input() - unlike the
equivalent methods on HikerCLI/Osintgram, which fuse fetch+compute+presentation
into one function body. This module is meant to be reused by any programmatic
caller (the web/LLM backend today).

Everything the web layer knows about Instagram goes through here: the
capabilities below are the single place that talks to a backend, so the app,
the tools handed to the model and any future caller share one implementation
(and one request counter, cache and budget).
"""
import configparser
import itertools
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from hikerapi import Client as AppClient


class OsintServiceError(Exception):
    """Base class for OsintgramService errors."""


class TargetNotFoundError(OsintServiceError):
    """The target Instagram username does not exist."""


class PrivateProfileError(OsintServiceError):
    """The requested capability needs a public profile but the target is private."""


class HikerAPIError(OsintServiceError):
    """HikerAPI returned an error or the request failed."""


class QueryCancelledError(Exception):
    """The user stopped the search (see _CountingApiProxy.cancelled).

    Deliberately NOT an OsintServiceError: the per-tool error handling turns
    those into an "error" result and carries on with the next tool, which
    would keep spending requests. This one is meant to unwind the whole run,
    so src/web/tools.py re-raises it instead of catching it.
    """


class RequestLimitReachedError(OsintServiceError):
    """The per-query cap on real (non-cached) backend requests was hit.

    Raised instead of making the request, not after - the caller (a tool
    method looping over pages/candidates) stops immediately rather than
    going even one request over the cap. See _CountingApiProxy.max_calls.
    """


# _contact_info makes one paid API request per candidate checked - tunable
# without touching the code since this is a direct cost/completeness tradeoff
# (higher finds more matches on accounts where few users set a public
# email/phone, at proportionally higher request cost).
DEFAULT_CONTACT_MAX_CHECKS = int(os.getenv("HIKER_CONTACT_MAX_CHECKS", "100"))


# A token typed into the web UI, kept for the life of the server process.
# Takes precedence over the config file (it is the more recent, more explicit
# choice) but not over HIKERAPI_TOKEN, which was set deliberately at launch -
# silently overriding that from a web form would make the env var lie.
_runtime_hiker_token: Optional[str] = None


def set_runtime_hiker_token(token: Optional[str]) -> None:
    global _runtime_hiker_token
    _runtime_hiker_token = (token or "").strip() or None


def hiker_token_source(credentials_path: str = "config/credentials.ini") -> Optional[str]:
    """Where the token in use comes from: "env", "runtime", "file" or None.

    Mirrors resolve_hiker_token's precedence exactly - the UI shows this so
    "I pasted a key and it still uses the old one" is visible rather than
    mysterious (it happens when HIKERAPI_TOKEN is set).
    """
    if os.getenv("HIKERAPI_TOKEN"):
        return "env"
    if _runtime_hiker_token:
        return "runtime"
    return "file" if _token_from_file(credentials_path) else None


def _token_from_file(credentials_path: str) -> Optional[str]:
    try:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(credentials_path)
        return parser.get("Credentials", "hikerapi_token", fallback=None) or None
    except Exception:
        return None


def save_hiker_token(token: str, credentials_path: str = "config/credentials.ini") -> None:
    """Persist the token to the same file (and key) the CLI reads, so a token
    Preserves whatever else is in the file - the instagrapi credentials live
    in the same section."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(credentials_path)
    if not parser.has_section("Credentials"):
        parser.add_section("Credentials")
    parser.set("Credentials", "hikerapi_token", token)
    directory = os.path.dirname(credentials_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(credentials_path, "w") as handle:
        parser.write(handle)
    # Credentials file: keep it readable only by its owner.
    try:
        os.chmod(credentials_path, 0o600)
    except OSError:
        pass  # best effort - some filesystems (mounted shares) refuse chmod


def resolve_hiker_token(credentials_path: str = "config/credentials.ini") -> Optional[str]:
    """Resolve the HikerAPI token: env var, then the key entered in the UI,
    then config/credentials.ini.

    Deliberately never raises and never exits: a missing or malformed config
    file must leave a long-running web server up (and able to ask for a key)
    rather than taking it down at import time.
    """
    token = os.getenv("HIKERAPI_TOKEN")
    if token:
        return token
    if _runtime_hiker_token:
        return _runtime_hiker_token
    try:
        return _token_from_file(credentials_path)
    except Exception:
        return None


# HikerAPI's current ("g2") endpoints return Instagram's GraphQL-shaped
# objects instead of the legacy private-API ones: numeric fields carry a type
# prefix ("1ltaken_at", "1flat", "1fposition" - no real Instagram field name
# starts with a digit, so the prefix is unambiguous) and user objects have
# "id" but no "pk". normalize_payload maps them back to the legacy field
# names every capability below reads, so none of them needs to care which
# endpoint generation (or backend) a response came from.
# Idempotent on legacy-shaped data, e.g. from the instagrapi backend.
_TYPED_KEY_PREFIX = re.compile(r"^1[a-z](?=[a-z_])")


def normalize_payload(value):
    if isinstance(value, list):
        return [normalize_payload(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            plain = _TYPED_KEY_PREFIX.sub("", key)
            item = normalize_payload(item)
            # Some responses carry both spellings ("1ltaken_at" and
            # "taken_at"), one of them empty - never let the empty one win.
            if plain in out and out[plain] is not None and item is None:
                continue
            out[plain] = item
        if "pk" not in out and "id" in out and "username" in out:
            out["pk"] = out["id"]
        return out
    return value


# A request can fail for a moment (dropped connection, read timeout, the
# backend answering 429/503) - retrying a couple of times with a short pause
# turns most of those into a result instead of a half-finished scan. Set
# HIKER_RETRY_ATTEMPTS=1 to disable retrying entirely.
RETRY_ATTEMPTS = max(1, int(os.getenv("HIKER_RETRY_ATTEMPTS", "3")))
RETRY_BASE_DELAY_SECONDS = float(os.getenv("HIKER_RETRY_DELAY", "0.6"))
# Transport-level failures: httpx raises these, HTTP status codes it doesn't.
_TRANSIENT_EXCEPTIONS = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)
# ...so a rate limit or a gateway error arrives as an ordinary error body.
_TRANSIENT_DETAIL = re.compile(r"\b(429|5\d\d)\b|rate.?limit|too many requests|timed? ?out|temporar", re.I)


def _retry_delay(attempt: int) -> float:
    """Back off a little more after each failed attempt."""
    return RETRY_BASE_DELAY_SECONDS * attempt


def _error_detail(result) -> Optional[str]:
    """The backend's error message, if this response is an error at all."""
    if isinstance(result, dict):
        detail = result.get("error") or result.get("detail")
        if detail:
            return str(detail)
    return None


def _transient_error_detail(result) -> Optional[str]:
    detail = _error_detail(result)
    return detail if detail and _TRANSIENT_DETAIL.search(detail) else None


class _CountingApiProxy:
    """Transparent wrapper that counts every method call made through it.

    A single OsintgramService capability can trigger many actual requests to
    the backend (pagination pages, one user_by_id_v2 per follower checked for
    contact info) - the tool-call count alone drastically understates real
    API usage. Wrapping the client here counts every underlying request
    regardless of which of its methods gets called, without needing to touch
    any of the call sites in this file.
    """

    def __init__(self, api_client):
        self._wrapped = api_client
        self.call_count = 0
        # Callback signature: (method_name, new_total, args, kwargs, status,
        # error_message) - status is "ok", "error" or "cached"; error_message
        # is set only for "error". Fired once per call, right after it
        # returns/raises (or is served from cache), so a caller (src/web/
        # app.py) gets a live event the instant each request happens/would
        # have happened, even mid-way through a single OsintgramService
        # method that loops over many of them (pagination, per-user lookups)
        # - args/kwargs are passed through so the caller can show which
        # specific user/page a request was for, not just "another
        # user_by_id_v2 call" indistinguishable from the last one.
        self.on_call = None
        # Optional per-raw-call cache, set by the caller (src/web/app.py)
        # after construction - None/ttl<=0 means disabled. Keyed on
        # (method_name, args, kwargs), so it's shared across every
        # OsintgramService/target built during the process lifetime: the
        # same user_by_id_v2(pk) lookup triggered by two different tools, or
        # even two different target accounts scanning overlapping follower
        # lists, is only ever actually requested once per TTL window. This
        # is finer-grained than (and independent of) app.py's whole-tool-
        # result cache, which only helps when a tool is called again with
        # the exact same arguments. Any object with dict-style get/item
        # assignment works (the web UI passes a SQLite-backed one, so it
        # also survives restarts); entries are (expires_at, result) with
        # expires_at in wall-clock unix seconds for that reason.
        self.cache_store: Optional[dict] = None
        self.cache_ttl_seconds: int = 0
        # Optional hard cap on real (non-cached) requests for the lifetime of
        # this proxy - i.e. for the whole query, since one OsintgramService/
        # api instance is shared across every tool call a query makes (see
        # src/web/app.py, which sets this from the "Limite chiamate" UI
        # value). A cache hit is free and never counts against it, so this
        # is genuinely "N requests actually sent to the backend", not "N
        # candidates considered".
        self.max_calls: Optional[int] = None
        # Optional threading.Event set when the user stops the search. Checked
        # before every real request so a cancelled query stops *spending*
        # immediately - aborting the browser's request alone would leave this
        # worker running (and billing) to completion.
        self.cancelled = None

    def __getattr__(self, name):
        attr = getattr(self._wrapped, name)
        if not callable(attr):
            return attr

        def _counted(*args, **kwargs):
            cache_key = None
            if self.cache_store is not None and self.cache_ttl_seconds > 0:
                cache_key = (name, args, tuple(sorted(kwargs.items())))
                cached = self.cache_store.get(cache_key)
                if cached is not None and time.time() < cached[0]:
                    if self.on_call:
                        self.on_call(name, self.call_count, args, kwargs, "cached", None)
                    return cached[1]

            # Checked after the cache lookup: serving an already-cached
            # response costs nothing and keeps the stop instantaneous.
            if self.cancelled is not None and self.cancelled.is_set():
                raise QueryCancelledError("Search stopped by the user.")

            if self.max_calls is not None and self.call_count >= self.max_calls:
                if self.on_call:
                    self.on_call(name, self.call_count, args, kwargs, "limit", None)
                raise RequestLimitReachedError(
                    f"Reached this search's limit of {self.max_calls} requests to Hiker/instagrapi."
                )

            # A dropped connection or a momentary 429/5xx is worth retrying:
            # the request was paid for either way, and without this one blip
            # ends a scan with partial results (see _retry_delay).
            for attempt in range(1, RETRY_ATTEMPTS + 1):
                last = attempt == RETRY_ATTEMPTS
                self.call_count += 1
                call_index = self.call_count
                try:
                    result = attr(*args, **kwargs)
                except _TRANSIENT_EXCEPTIONS as e:
                    if last or self._stop_requested():
                        if self.on_call:
                            self.on_call(name, call_index, args, kwargs, "error", str(e))
                        raise
                    if self.on_call:
                        self.on_call(name, call_index, args, kwargs, "retry", str(e))
                    time.sleep(_retry_delay(attempt))
                    continue
                except Exception as e:
                    if self.on_call:
                        self.on_call(name, call_index, args, kwargs, "error", str(e))
                    raise

                # HikerAPI reports failures in the body (its client never
                # raises on status), so a transient one looks like a normal
                # return value - hence this check rather than an exception.
                transient = _transient_error_detail(result)
                if transient and not last and not self._stop_requested():
                    if self.on_call:
                        self.on_call(name, call_index, args, kwargs, "retry", transient)
                    time.sleep(_retry_delay(attempt))
                    continue

                # Never cache an error body: a transient failure must not get
                # "stuck" for the whole TTL.
                if cache_key is not None and not _error_detail(result):
                    self.cache_store[cache_key] = (time.time() + self.cache_ttl_seconds, result)
                if self.on_call:
                    self.on_call(name, call_index, args, kwargs, "ok", None)
                return result

        return _counted

    def _stop_requested(self) -> bool:
        return self.cancelled is not None and self.cancelled.is_set()


class OsintgramService:
    """Stateless-per-instance wrapper around a target's Instagram data.

    `api_client` is any object implementing the eight HikerAPI-shaped methods
    used below (user_by_username_v2, user_medias_g2, media_comments_v2,
    user_followers_g2, user_following_g2, user_tag_medias_v2,
    user_stories_v2, user_by_id_v2) - either hikerapi's own Client, or
    src.instagrapi_backend.InstagrapiClient. See build_service() below for
    the backend-selection logic; construct this directly only if you already
    have a client instance.
    """

    def __init__(self, target: str, api_client):
        self._backend_client = api_client
        self.api = _CountingApiProxy(api_client)
        self.geolocator = Nominatim(user_agent="osintgram-web")
        # Nominatim's usage policy caps requests at 1/second; without this,
        # reverse-geocoding more than one location in get_addrs gets
        # rate-limited/blocked and fails the whole request instead of just
        # that one lookup. swallow_exceptions=True turns a failed lookup
        # (after retries) into a None result instead of an exception.
        self._reverse_geocode = RateLimiter(
            self.geolocator.reverse, min_delay_seconds=1, max_retries=2, swallow_exceptions=True
        )
        # `target` may be None: hashtag/place searches don't belong to any
        # account, and resolving one would cost a request for nothing. The
        # capabilities that do need a target call _require_target().
        self.target = target
        self.user = self._fetch_user(target) if target else {}
        self.target_id = self.user.get("pk")
        self.is_private = bool(self.user.get("is_private"))

    @property
    def backend_name(self) -> str:
        """Human-readable name of the backend behind self.api, for the web
        UI's verbose trace ("which API is being called")."""
        return {"Client": "HikerAPI", "InstagrapiClient": "instagrapi"}.get(
            type(self._backend_client).__name__, type(self._backend_client).__name__
        )

    @property
    def api_call_count(self) -> int:
        """Number of actual requests made to the backend client so far -
        the real cost signal, since one capability can make many (pagination,
        per-user lookups for contact info)."""
        return self.api.call_count

    def _fetch_user(self, username: str) -> dict:
        try:
            data = self.api.user_by_username_v2(username)
        except Exception as e:
            raise HikerAPIError(str(e)) from e
        if "error" in data:
            raise HikerAPIError(str(data["error"]))
        if "detail" in data:
            raise TargetNotFoundError(f"@{username} not found: {data['detail']}")
        return data["user"]

    def _require_target(self) -> None:
        if not self.target_id:
            raise OsintServiceError("This command needs a target username.")

    def _require_public(self) -> None:
        self._require_target()
        if self.is_private:
            raise PrivateProfileError(f"@{self.target} has a private profile")

    def _iter_items(self, api_method, results_key: str, cursor_param: str = "page_id", user_id=None):
        """Yield a user's items page by page, normalized (see normalize_payload).

        Lazy, so a caller that stops early never fetches a page it doesn't
        need. `cursor_param` is the keyword the endpoint takes the previous
        response's next_page_id under - "page_id" for most, but
        user_medias_g2 calls it "next_page_id". `user_id` defaults to the
        target, but compare_with passes another account's id so both accounts'
        lists go through the same api proxy (one shared counter and budget).
        """
        subject = self.target_id if user_id is None else user_id
        next_page_id = None
        while True:
            try:
                result = api_method(subject, **({cursor_param: next_page_id} if next_page_id else {}))
            except RequestLimitReachedError:
                # The per-query request budget ran out mid-scan - end here
                # with whatever pages were already fetched instead of failing
                # the whole tool call; a shorter-than-asked-for list is still
                # a valid, usable answer, not an error.
                return
            yield from normalize_payload(result.get("response", {}).get(results_key, []))
            next_page_id = result.get("next_page_id")
            if not next_page_id:
                return

    def _paginate(
        self, api_method, results_key: str, limit: Optional[int] = None, cursor_param: str = "page_id", user_id=None
    ) -> list:
        return list(itertools.islice(self._iter_items(api_method, results_key, cursor_param, user_id), limit))

    def _get_feed(self, limit: Optional[int] = None) -> list:
        return self._paginate(self.api.user_medias_g2, "items", limit=limit, cursor_param="next_page_id")

    def _get_comments(self, media_id, limit: Optional[int] = None) -> list:
        data = []
        next_page_id = ""
        while True:
            try:
                result = self.api.media_comments_v2(media_id, page_id=next_page_id)
            except RequestLimitReachedError:
                return data  # budget ran out mid-scan - return what we have
            except Exception as e:
                if "Entries not found" in str(e):
                    return data
                raise HikerAPIError(str(e)) from e
            data.extend(result.get("response", {}).get("comments", []))
            next_page_id = result.get("next_page_id")
            if limit is not None and len(data) >= limit:
                return data[:limit]
            if not next_page_id:
                break
        return data

    @staticmethod
    def _summarize_user(user: dict) -> dict:
        return {
            "id": user["pk"],
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "is_private": user.get("is_private"),
            "is_verified": user.get("is_verified"),
        }

    _MEDIA_TYPE_NAMES = {1: "photo", 2: "video", 8: "carousel"}

    @staticmethod
    def _media_files(media: dict) -> dict:
        """Direct CDN URLs for one photo/video (a post or a carousel slide):
        a small thumbnail for the grid, and the original file - the .mp4 for
        a video, the largest image for a photo - to open without going
        through instagram.com (same as get_user_stories)."""
        candidates = (media.get("image_versions2") or {}).get("candidates") or []
        # Thumbnail: smallest candidate still >= 320px wide - a grid tile
        # doesn't need the full-size original. Falls back to the first one
        # when no sizes are given (instagrapi).
        sized = [c for c in candidates if (c.get("width") or 0) >= 320]
        thumbnail = min(sized, key=lambda c: c["width"]) if sized else (candidates[0] if candidates else {})
        largest = max(candidates, key=lambda c: c.get("width") or 0) if candidates else {}
        videos = media.get("video_versions") or []
        # Instagram lists video_versions best-first.
        media_url = videos[0].get("url") if media.get("media_type") == 2 and videos else largest.get("url")
        return {
            "media_type": OsintgramService._MEDIA_TYPE_NAMES.get(media.get("media_type"), "other"),
            "thumbnail_url": thumbnail.get("url"),
            "media_url": media_url,
        }

    @staticmethod
    def _post_preview(post: dict) -> dict:
        """Compact summary of one post for the web UI's expandable preview
        grid: thumbnail, direct link to the media file, and its counters.
        Returned under a "previews" key by the post-summary capabilities -
        src/web/app.py strips it before results reach the LLM, which has no
        use for media URLs.

        A carousel gets one entry per slide in "slides"; its own
        thumbnail_url/media_url are its cover (its first slide when the
        backend gives no separate cover - instagrapi)."""
        slides = [OsintgramService._media_files(s) for s in post.get("carousel_media") or []]
        files = OsintgramService._media_files(post)
        if slides and not files["thumbnail_url"]:
            files = {**slides[0], "media_type": files["media_type"]}
        code = post.get("code")
        path = "reel" if post.get("product_type") == "clips" else "p"
        caption = (post.get("caption") or {}).get("text") or ""
        return {
            "id": post.get("id"),
            **files,
            "slides": slides or None,
            "permalink": f"https://www.instagram.com/{path}/{code}/" if code else None,
            "like_count": post.get("like_count"),
            "comment_count": post.get("comment_count"),
            "play_count": OsintgramService._play_count(post),
            "taken_at": post.get("taken_at"),
            "caption": caption[:120],
            "coauthors": OsintgramService._coauthors(post),
            "paid_partnership": bool(post.get("is_paid_partnership")),
            "audio": OsintgramService._audio_label(post),
            # Who posted it - the key column when the posts aren't the
            # target's own (hashtag and place searches).
            "author": (post.get("user") or {}).get("username"),
        }

    @staticmethod
    def _play_count(post: dict) -> Optional[int]:
        return post.get("play_count") or post.get("ig_play_count") or post.get("view_count")

    @staticmethod
    def _coauthors(post: dict) -> list:
        """Usernames of the post's collab co-authors (besides the target)."""
        return [u.get("username") for u in post.get("coauthor_producers") or [] if u.get("username")]

    @staticmethod
    def _audio_label(post: dict) -> Optional[str]:
        """"Title — Artist" of the song or original sound used, if any.
        Reels carry it in clips_metadata, other posts in music_metadata."""
        for meta in (post.get("clips_metadata"), post.get("music_metadata")):
            if not meta:
                continue
            song = (meta.get("music_info") or {}).get("music_asset_info") or {}
            if song.get("title"):
                return " — ".join(filter(None, [song["title"], song.get("display_artist")]))
            sound = meta.get("original_sound_info") or {}
            if sound.get("original_audio_title"):
                artist = (sound.get("ig_artist") or {}).get("username")
                return " — ".join(filter(None, [sound["original_audio_title"], artist and f"@{artist}"]))
        return None

    # ---- capabilities ----

    # Everything else worth keeping out of the profile object, which the
    # backends return in full. Listed explicitly rather than passed through
    # wholesale: the raw object carries dozens of internal flags
    # (has_anonymous_profile_picture, is_supervision_features_enabled...) that
    # would bury the useful fields in the UI and waste the model's context.
    # A key missing from a given backend's payload is simply skipped, so
    # listing generously here costs nothing.
    _EXTRA_PROFILE_FIELDS = (
        # Link in bio - often the most useful single field on a profile.
        "external_url",
        # Public contact details, set by business/creator accounts.
        "public_email",
        "contact_phone_number",
        "public_phone_country_code",
        "public_phone_number",
        "whatsapp_number",
        "business_contact_method",
        # Business address, down to the coordinates Instagram stores for it.
        "address_street",
        "city_name",
        "zip",
        "latitude",
        "longitude",
        "instagram_location_id",
        # What kind of account it is.
        "category",
        "category_name",
        "business_category_name",
        "account_type",
        "is_memorialized",
        # The linked Facebook account id - a cross-platform pivot.
        "fbid_v2",
        # Content counters the profile object already knows, no feed scan needed.
        "total_clips_count",
        "total_igtv_videos",
        "usertags_count",
        "highlight_reel_count",
    )

    def get_user_info(self) -> dict:
        self._require_target()
        data = self.user
        info = {
            "id": data["pk"],
            "username": self.target,
            "full_name": data.get("full_name"),
            "biography": data.get("biography"),
            "follower_count": data.get("follower_count"),
            "following_count": data.get("following_count"),
            "media_count": data.get("media_count"),
            "is_private": data.get("is_private"),
            "is_business": data.get("is_business"),
            "is_verified": data.get("is_verified"),
            "profile_pic_url_hd": (data.get("hd_profile_pic_url_info") or {}).get("url"),
        }
        for key in self._EXTRA_PROFILE_FIELDS:
            if data.get(key) not in (None, "", [], {}):
                info[key] = data[key]

        # Modern profiles carry several links, not just external_url; each one
        # is {"title": ..., "url": ..., "lynx_url": ...} (lynx_url is
        # Instagram's click tracker, so prefer the real destination).
        links = [
            {"title": link.get("title") or None, "url": link.get("url") or link.get("lynx_url")}
            for link in (data.get("bio_links") or [])
            if isinstance(link, dict) and (link.get("url") or link.get("lynx_url"))
        ]
        if links:
            info["bio_links"] = links
        # A list of strings upstream; joined so it reads as one value.
        pronouns = [p for p in (data.get("pronouns") or []) if p]
        if pronouns:
            info["pronouns"] = "/".join(pronouns)
        return info

    def get_account_about(self) -> dict:
        """Instagram's own "About this account" panel: which country the
        account is registered in, roughly when it was created, and how many
        times its username changed. Costs one extra request (it is a separate
        endpoint, not part of the profile object).

        Two limits come from Instagram, not from here: the creation date has
        month precision ("January 2020", no day), and the former usernames are
        only ever reported as a *count* - the panel says "2 username changes"
        and never which ones, so no backend can return the old names."""
        self._require_target()
        data = normalize_payload(self.api.user_about_gql(str(self.target_id)))
        if not isinstance(data, dict) or not data:
            return {"username": self.target, "error": "No \"About this account\" data available."}
        info = {
            "username": data.get("username") or self.target,
            "is_verified": data.get("is_verified"),
            "country": data.get("country") or None,
            "date_joined": data.get("date") or None,
        }
        # Upstream sends this as a string: "" for none, otherwise a digit count
        # ("2"). Checked on several accounts - never actual usernames, despite
        # HikerAPI documenting it as "the list of former usernames". Handle the
        # documented shape too, in case it ever starts arriving.
        former = str(data.get("former_usernames") or "").strip()
        if former.isdigit():
            info["former_usernames_count"] = int(former)
        elif former:
            names = [u.strip() for u in re.split(r"[,\n]", former) if u.strip()]
            info["former_usernames_count"] = len(names)
            info["former_usernames"] = names
        else:
            info["former_usernames_count"] = 0
        return info

    def get_followers(self, limit: Optional[int] = 200) -> list:
        self._require_public()
        users = self._paginate(self.api.user_followers_g2, "users", limit=limit)
        return [self._summarize_user(u) for u in users]

    def get_followings(self, limit: Optional[int] = 200) -> list:
        self._require_public()
        users = self._paginate(self.api.user_following_g2, "users", limit=limit)
        return [self._summarize_user(u) for u in users]

    def get_hashtags(self, limit_posts: Optional[int] = None) -> list:
        self._require_public()
        data = self._get_feed(limit=limit_posts)
        counter: dict = {}
        for post in data:
            caption = post.get("caption")
            if not caption:
                continue
            for word in (caption.get("text") or "").split():
                if word.startswith("#"):
                    counter[word] = counter.get(word, 0) + 1
        ranked = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)
        return [{"hashtag": h, "count": c} for h, c in ranked]

    def get_addrs(self, limit_posts: Optional[int] = None) -> list:
        self._require_public()
        data = self._get_feed(limit=limit_posts)
        # Keyed by rounded coords so several posts at the same place collapse
        # to one entry (keeping the most recent taken_at); lat/lng are carried
        # through so the web UI can plot them on a map, not just list them.
        locations = {}
        for post in data:
            location = post.get("location")
            if location and location.get("lat") is not None and location.get("lng") is not None:
                lat, lng = location["lat"], location["lng"]
                key = f"{lat}, {lng}"
                taken_at = post.get("taken_at")
                prev = locations.get(key)
                if prev is None or (taken_at or 0) > (prev[1] or 0):
                    locations[key] = (lat, lng, taken_at, location.get("name"))

        addresses = []
        failed = 0
        for coords, (lat, lng, taken_at, name) in locations.items():
            details = self._reverse_geocode(coords)
            if details is None:
                failed += 1
                continue
            when = (
                datetime.fromtimestamp(taken_at).strftime("%Y-%m-%d %H:%M:%S")
                if taken_at
                else None
            )
            addresses.append({
                "address": details.address,
                "name": name,
                "lat": lat,
                "lng": lng,
                "time": when,
            })

        # swallow_exceptions on the rate limiter turns every failed lookup
        # into a silent None - without this check, a broken geocoding setup
        # (e.g. no local CA certs) would look identical to "no addresses
        # found" instead of surfacing as an error.
        if locations and failed == len(locations):
            raise HikerAPIError(
                f"reverse geocoding failed for all {failed} location(s) - "
                "the geocoding service (Nominatim) may be unreachable "
                "(check network/SSL configuration)"
            )

        return sorted(addresses, key=lambda a: a["time"] or "", reverse=True)

    def get_captions(self, limit_posts: Optional[int] = None) -> list:
        self._require_public()
        data = self._get_feed(limit=limit_posts)
        captions = []
        for item in data:
            caption = item.get("caption")
            if caption and caption.get("text"):
                captions.append(caption["text"])
        return captions

    def get_total_comments(self, limit_posts: Optional[int] = None) -> dict:
        self._require_public()
        data = self._get_feed(limit=limit_posts)
        counts = [int(p.get("comment_count", 0)) for p in data]
        posts = len(counts)
        if posts == 0:
            return {"comment_counter": 0, "posts": 0, "min": 0, "max": 0, "avg": 0, "previews": []}
        total = sum(counts)
        return {
            "comment_counter": total,
            "posts": posts,
            "min": min(counts),
            "max": max(counts),
            "avg": total // posts,
            "previews": [self._post_preview(p) for p in data],
        }

    def get_total_likes(self, limit_posts: Optional[int] = None) -> dict:
        self._require_public()
        data = self._get_feed(limit=limit_posts)
        counts = [int(p.get("like_count", 0)) for p in data]
        posts = len(counts)
        if posts == 0:
            return {"like_counter": 0, "posts": 0, "min": 0, "max": 0, "avg": 0, "previews": []}
        total = sum(counts)
        return {
            "like_counter": total,
            "posts": posts,
            "min": min(counts),
            "max": max(counts),
            "avg": total // posts,
            "previews": [self._post_preview(p) for p in data],
        }

    def get_media_type(self, limit_posts: Optional[int] = None) -> dict:
        self._require_public()
        data = self._get_feed(limit=limit_posts)
        photos = sum(1 for p in data if p.get("media_type") == 1)
        videos = sum(1 for p in data if p.get("media_type") == 2)
        # media_type 8 = carousel/album (several photos/videos in one post).
        carousels = sum(1 for p in data if p.get("media_type") == 8)
        plays = [n for n in (self._play_count(p) for p in data if p.get("media_type") == 2) if n]
        return {
            "photos": photos,
            "videos": videos,
            "carousels": carousels,
            "total": len(data),
            "video_plays_total": sum(plays),
            "video_plays_avg": sum(plays) // len(plays) if plays else 0,
            "collaborations": sum(1 for p in data if self._coauthors(p)),
            "paid_partnerships": sum(1 for p in data if p.get("is_paid_partnership")),
            "previews": [self._post_preview(p) for p in data],
        }

    def get_posting_times(self, limit_posts: Optional[int] = None) -> dict:
        """When the target posts: per weekday/hour counts (UTC, since the
        target's own timezone is unknown), the busiest slot, and posting
        frequency. "timestamps" (UI-only, stripped for the LLM by
        src/web/app.py) lets the web UI redraw the heatmap in the viewer's
        own timezone."""
        self._require_public()
        times = sorted(p["taken_at"] for p in self._get_feed(limit=limit_posts) if p.get("taken_at"))
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        by_weekday = dict.fromkeys(weekdays, 0)
        by_hour = {f"{h:02d}": 0 for h in range(24)}
        for t in times:
            when = datetime.fromtimestamp(t, tz=timezone.utc)
            by_weekday[weekdays[when.weekday()]] += 1
            by_hour[f"{when.hour:02d}"] += 1
        if not times:
            return {"posts": 0, "timezone": "UTC", "by_weekday": by_weekday, "by_hour": by_hour, "timestamps": []}
        busiest_hour = int(max(by_hour, key=by_hour.get))
        gaps = [(b - a) / 86400 for a, b in zip(times, times[1:])]
        return {
            "posts": len(times),
            "timezone": "UTC",
            "most_active_day": max(by_weekday, key=by_weekday.get),
            "most_active_hour": f"{busiest_hour:02d}:00-{(busiest_hour + 1) % 24:02d}:00",
            "first_post": datetime.fromtimestamp(times[0], tz=timezone.utc).strftime("%Y-%m-%d"),
            "last_post": datetime.fromtimestamp(times[-1], tz=timezone.utc).strftime("%Y-%m-%d"),
            "avg_days_between_posts": round(sum(gaps) / len(gaps), 1) if gaps else None,
            "by_weekday": by_weekday,
            "by_hour": by_hour,
            "timestamps": times,
        }

    def get_photo_descriptions(self, limit_posts: Optional[int] = None) -> dict:
        """Alt text of the target's photos, carousel slides included (their
        accessibility_caption - the field the CLI's `photodes` used to read).

        Instagram no longer exposes its automatic "May be an image of..."
        descriptions here: the field is only filled when the post's author
        wrote alt text themselves, so on most accounts it's empty for every
        photo. photos_scanned/with_alt_text say how many were checked, so an
        empty list reads as "none of N photos has one", not as a failure.
        """
        self._require_public()
        photos = [
            (media, post)
            for post in self._get_feed(limit=limit_posts)
            for media in post.get("carousel_media") or [post]
            if media.get("media_type") == 1
        ]
        descriptions = [
            {
                "description": media["accessibility_caption"],
                "taken_at": media.get("taken_at") or post.get("taken_at"),
                **self._media_files(media),
            }
            for media, post in photos
            if media.get("accessibility_caption")
        ]
        return {"photos_scanned": len(photos), "with_alt_text": len(descriptions), "descriptions": descriptions}

    def get_comment_data(self, limit_posts: Optional[int] = None) -> list:
        self._require_public()
        data = self._get_feed(limit=limit_posts)
        comments = []
        for post in data:
            post_id = post.get("id")
            for comment in self._get_comments(post_id):
                comments.append(
                    {
                        "post_id": post_id,
                        "user_id": comment.get("user_id"),
                        "username": (comment.get("user") or {}).get("username"),
                        "comment": comment.get("text"),
                    }
                )
        return comments

    def get_people_who_commented(self, limit_posts: Optional[int] = None) -> list:
        self._require_public()
        data = self._get_feed(limit=limit_posts)
        users: dict = {}
        for post in data:
            for comment in self._get_comments(post.get("id")):
                user = comment.get("user") or {}
                pk = user.get("pk")
                if pk is None:
                    continue
                if pk in users:
                    users[pk]["counter"] += 1
                else:
                    users[pk] = {
                        "id": pk,
                        "username": user.get("username"),
                        "full_name": user.get("full_name"),
                        "counter": 1,
                    }
        return sorted(users.values(), key=lambda u: u["counter"], reverse=True)

    def get_people_who_tagged(self, limit: Optional[int] = None) -> list:
        self._require_public()
        posts = self._paginate(self.api.user_tag_medias_v2, "items", limit=limit)
        users: dict = {}
        for post in posts:
            tag = post.get("user") or {}
            pk = tag.get("pk")
            if pk is None:
                continue
            if pk in users:
                users[pk]["counter"] += 1
            else:
                users[pk] = {
                    "id": pk,
                    "username": tag.get("username"),
                    "full_name": tag.get("full_name"),
                    "counter": 1,
                }
        return sorted(users.values(), key=lambda u: u["counter"], reverse=True)

    def get_people_tagged_by_user(self, limit_posts: Optional[int] = None) -> list:
        # No private-profile guard, matching the original CLI behavior.
        self._require_target()
        data = self._get_feed(limit=limit_posts)
        tagged: dict = {}
        for post in data:
            usertags = post.get("usertags") or []
            # HikerAPI nests the tag list as {"in": [...]}; the instagrapi
            # backend returns the list directly.
            if isinstance(usertags, dict):
                usertags = usertags.get("in") or []
            for tag in usertags:
                user = tag.get("user") or {}
                pk = user.get("pk")
                if pk is None:
                    continue
                if pk in tagged:
                    tagged[pk]["posts"] += 1
                else:
                    tagged[pk] = {
                        "id": pk,
                        "username": user.get("username"),
                        "full_name": user.get("full_name"),
                        "posts": 1,
                    }
        return sorted(tagged.values(), key=lambda u: u["posts"], reverse=True)

    def get_user_photos(self, limit: Optional[int] = None) -> list:
        # Iterates the feed lazily rather than via _get_feed(limit=limit):
        # `limit` counts photos, not posts, and a post can yield zero photos
        # (a video) or several (a carousel), so the two can't share one cap -
        # capping the post fetch by the photo limit would under-count whenever
        # videos are mixed into the scanned posts.
        #
        # Photos are picked by media_type, not by the presence of
        # image_versions2: every post has one (a video's cover, a carousel's
        # first slide), so that alone would return video covers as photos and
        # only the first slide of each carousel.
        self._require_public()
        photos = []
        for item in self._iter_items(self.api.user_medias_g2, "items", cursor_param="next_page_id"):
            candidates = (item.get("carousel_media") or []) if item.get("media_type") == 8 else [item]
            for media in candidates:
                if media.get("media_type") != 1:
                    continue
                if limit is not None and len(photos) >= limit:
                    return photos
                versions = (media.get("image_versions2") or {}).get("candidates", [])
                if versions:
                    photos.append({"id": media.get("id"), "url": versions[0]["url"]})
        return photos

    def get_user_propic(self) -> dict:
        # No private-profile guard, matching the original CLI behavior.
        self._require_target()
        data = self.user
        info = data.get("hd_profile_pic_url_info")
        if info and info.get("url"):
            return {"url": info["url"]}
        versions = data.get("hd_profile_pic_versions") or []
        if versions:
            return {"url": versions[-1]["url"]}
        raise HikerAPIError("No profile picture available")

    def get_user_stories(self) -> list:
        self._require_public()
        try:
            data = self.api.user_stories_v2(self.target_id)
        except RequestLimitReachedError:
            return []  # budget already spent - no stories rather than an error
        reel = data.get("reel")
        if not reel:
            return []
        stories = []
        for item in reel.get("items", []):
            # For a photo this is the photo itself; for a video it's the
            # cover frame - returned as thumbnail_url so a video story can be
            # previewed without loading the video (`url` is the .mp4).
            image_candidates = (item.get("image_versions2") or {}).get("candidates") or []
            image_url = image_candidates[0].get("url") if image_candidates else None
            if item.get("media_type") == 1 and image_url:
                story = {"id": item.get("id"), "media_type": "photo", "url": image_url}
            elif item.get("media_type") == 2 and item.get("video_versions"):
                story = {"id": item.get("id"), "media_type": "video", "url": item["video_versions"][0]["url"]}
                if image_url:
                    story["thumbnail_url"] = image_url
            else:
                continue
            stories.append(story)
        return stories

    def get_highlights(self) -> list:
        """The target's Story Highlights (the archived stories pinned on the
        profile): title, how many stories each holds, cover image and when it
        was created / last updated. Reaches back long after normal stories
        expire."""
        self._require_public()
        try:
            data = self.api.user_highlights_v2(self.target_id)
        except RequestLimitReachedError:
            return []
        tray = data.get("response", {}).get("tray") or []
        highlights = []
        for item in tray:
            cover = item.get("cover_media") or {}
            image = cover.get("cropped_image_version") or cover.get("full_image_version") or {}
            highlights.append({
                # "highlight:123..." -> the numeric id used by instagram.com/stories/highlights/<id>/
                "id": (item.get("id") or "").split(":")[-1] or None,
                "title": item.get("title"),
                "media_count": item.get("media_count"),
                "thumbnail_url": image.get("url"),
                "created_at": item.get("created_at"),
                "last_updated": item.get("latest_reel_media"),
            })
        return highlights

    def get_suggested_profiles(self) -> list:
        """Accounts Instagram suggests as related to the target (the "Suggested
        for you" chaining list) - often the target's real circle: alternate
        accounts, friends, the same person's other profiles."""
        try:
            data = self.api.user_suggested_profiles_v2(self.target_id)
        except RequestLimitReachedError:
            return []
        suggestions = []
        for user in normalize_payload(data.get("users") or []):
            entry = self._summarize_user(user)
            context = user.get("social_context")
            # Instagram often just echoes the full name here - only keep it
            # when it actually says something ("Followed by ...", "Popular").
            if context and context != user.get("full_name"):
                entry["context"] = context
            suggestions.append(entry)
        return suggestions

    # ---- searches that belong to no account (no target needed) ----

    @staticmethod
    def _v1_media_to_legacy(media: dict) -> dict:
        """Map the "v1 chunk" media shape (location feeds: thumbnail_url,
        video_url, caption_text, an ISO taken_at) onto the legacy one every
        preview/extractor here already understands."""
        out = dict(media)
        if media.get("thumbnail_url") and not media.get("image_versions2"):
            out["image_versions2"] = {"candidates": [{"url": media["thumbnail_url"]}]}
        if media.get("video_url") and not media.get("video_versions"):
            out["video_versions"] = [{"url": media["video_url"]}]
        if media.get("caption_text") and not media.get("caption"):
            out["caption"] = {"text": media["caption_text"]}
        # taken_at is an ISO string here; taken_at_ts carries the epoch.
        if isinstance(media.get("taken_at"), str) or media.get("taken_at_ts"):
            out["taken_at"] = media.get("taken_at_ts")
        if media.get("resources"):
            out["carousel_media"] = [OsintgramService._v1_media_to_legacy(r) for r in media["resources"]]
        return out

    @staticmethod
    def _authors(posts: list) -> list:
        """Who posted, most prolific first - the point of a hashtag/place search."""
        counts: dict = {}
        for post in posts:
            user = post.get("user") or {}
            username = user.get("username")
            if not username:
                continue
            entry = counts.setdefault(username, {"username": username, "full_name": user.get("full_name"), "posts": 0})
            entry["posts"] += 1
        return sorted(counts.values(), key=lambda u: u["posts"], reverse=True)

    def search_hashtag(self, hashtag: str, sort: str = "top", limit: Optional[int] = 30) -> dict:
        """Posts published with a hashtag, newest ("recent") or most popular
        ("top") first, with who posted them. Needs no target account."""
        name = (hashtag or "").strip().lstrip("#")
        if not name:
            raise OsintServiceError("Specify a hashtag to search for.")
        if sort not in ("top", "recent"):
            raise OsintServiceError(f"invalid sort: {sort!r} (use top or recent)")
        method = self.api.hashtag_medias_top_v2 if sort == "top" else self.api.hashtag_medias_recent_v2

        posts = []
        page_id = None
        while limit is None or len(posts) < limit:
            try:
                result = method(name, **({"page_id": page_id} if page_id else {}))
            except RequestLimitReachedError:
                break  # budget spent mid-scan - return what we already have
            response = normalize_payload(result.get("response") or {})
            # HikerAPI's hashtag feeds come wrapped in "sections" of
            # "layout_content"; the instagrapi backend has no such grouping
            # and answers a plain "items" list, like every other feed.
            for section in response.get("sections") or []:
                for entry in (section.get("layout_content") or {}).get("medias") or []:
                    if entry.get("media"):
                        posts.append(entry["media"])
            posts.extend(self._v1_media_to_legacy(m) for m in response.get("items") or [])
            page_id = result.get("next_page_id")
            if not page_id:
                break
        posts = posts[:limit] if limit is not None else posts

        return {
            "hashtag": f"#{name}",
            "sort": sort,
            "posts": len(posts),
            "authors": self._authors(posts),
            "previews": [self._post_preview(p) for p in posts],
        }

    def search_location(self, place: str, limit: Optional[int] = 30) -> dict:
        """Recent posts published from a place, with who posted them. Resolves
        the place by name first (Instagram's own place search), so the result
        also says which place was matched. Needs no target account."""
        query = (place or "").strip()
        if not query:
            raise OsintServiceError("Specify a place to search for.")
        try:
            found = normalize_payload(self.api.fbsearch_places_v2(query))
        except RequestLimitReachedError:
            return {"place": None, "posts": 0, "authors": [], "previews": [], "alternatives": []}
        places = [item.get("location") or {} for item in found.get("items") or []]
        places = [p for p in places if p.get("pk")]
        if not places:
            raise OsintServiceError(f"No place found for {query!r}.")

        matched = places[0]
        posts = []
        max_id = None
        while limit is None or len(posts) < limit:
            try:
                chunk = self.api.location_medias_recent_chunk_v1(
                    int(matched["pk"]), **({"max_id": max_id} if max_id else {}))
            except RequestLimitReachedError:
                break
            # This endpoint answers [medias, next_max_id].
            medias, max_id = (chunk + [None, None])[:2] if isinstance(chunk, list) else ([], None)
            posts.extend(self._v1_media_to_legacy(m) for m in normalize_payload(medias or []))
            if not max_id or not medias:
                break
        posts = posts[:limit] if limit is not None else posts

        return {
            "place": {
                "name": matched.get("name"),
                "address": matched.get("address"),
                "city": matched.get("city"),
                "lat": matched.get("lat"),
                "lng": matched.get("lng"),
            },
            "alternatives": [p.get("name") for p in places[1:6]],
            "posts": len(posts),
            "authors": self._authors(posts),
            "previews": [self._post_preview(p) for p in posts],
        }

    def compare_with(self, other_username: str, scope: str = "both", limit: Optional[int] = 500) -> dict:
        """Overlap between the target and another public account: accounts that
        follow both, and accounts both of them follow (mutual connections).

        `scope` picks which side(s) to compare - "followers", "followings" or
        "both" - so a one-sided comparison costs half the requests. `limit`
        caps how many followers/followings are pulled from each side. Costs a
        lot of requests (both accounts' lists).

        Both accounts' lists go through this service's own api proxy (with the
        other account's id), so the request counter, cache and budget are the
        single shared ones - no second service, no counter juggling."""
        scope = (scope or "both").lower()
        if scope not in ("followers", "followings", "both"):
            raise OsintServiceError(f"invalid scope: {scope!r} (use followers, followings or both)")
        self._require_public()
        other = normalize_payload(self._fetch_user(other_username))
        if other.get("is_private"):
            raise PrivateProfileError(f"@{other_username} has a private profile")
        other_id = other["pk"]

        def common(mine, theirs):
            by_pk = {u["pk"]: u for u in mine}
            return [self._summarize_user(by_pk[u["pk"]]) for u in theirs if u["pk"] in by_pk]

        result = {"target": self.target, "other": other.get("username") or other_username, "scope": scope}
        scanned = {}
        if scope in ("followers", "both"):
            mine = self._paginate(self.api.user_followers_g2, "users", limit=limit)
            theirs = self._paginate(self.api.user_followers_g2, "users", limit=limit, user_id=other_id)
            result["common_followers"] = common(mine, theirs)
            scanned["target_followers"] = len(mine)
            scanned["other_followers"] = len(theirs)
        if scope in ("followings", "both"):
            mine = self._paginate(self.api.user_following_g2, "users", limit=limit)
            theirs = self._paginate(self.api.user_following_g2, "users", limit=limit, user_id=other_id)
            result["common_followings"] = common(mine, theirs)
            scanned["target_followings"] = len(mine)
            scanned["other_followings"] = len(theirs)
        result["scanned"] = scanned
        return result

    def _contact_info(
        self,
        api_method,
        from_key: str,
        to_key: str,
        match_limit: int = 20,
        max_checks: int = DEFAULT_CONTACT_MAX_CHECKS,
    ) -> list:
        """Port of HikerCLI.get_contact_info, minus the interactive prompts.

        Adds a hard `max_checks` cap on top of the CLI's behavior: the CLI
        scans the full follower/following list (one paid user_by_id_v2 call
        per user) until it finds `match_limit` matches, because a human was
        expected to pick a sane number first. Here a tool call can be issued
        by the LLM without that judgment call, so the scan is bounded.
        """
        self._require_public()
        # Bounded by max_checks: we never look at more candidates than that,
        # so there's no reason to page through the full follower/following
        # list first (that alone can be thousands of requests on a big account).
        # Both match_limit and max_checks are Optional[int] - the model can
        # send a sentinel like "unset"/"all" that _coerce_int turns into
        # None (meaning "no limit" here, same convention _paginate already
        # uses), so neither comparison below can assume a real int.
        candidates = self._paginate(api_method, "users", limit=max_checks)
        results = []
        checked = 0
        for user in candidates:
            if (match_limit is not None and len(results) >= match_limit) or (
                max_checks is not None and checked >= max_checks
            ):
                break
            checked += 1
            try:
                detail = self.api.user_by_id_v2(user["pk"])
            except RequestLimitReachedError:
                break  # budget ran out mid-scan - return the matches found so far
            value = (detail.get("user") or {}).get(from_key)
            if value:
                results.append(
                    {
                        "id": user["pk"],
                        "username": user.get("username"),
                        "full_name": user.get("full_name"),
                        to_key: value,
                    }
                )
        return results

    def get_followers_email(self, match_limit: int = 20, max_checks: int = DEFAULT_CONTACT_MAX_CHECKS) -> list:
        return self._contact_info(self.api.user_followers_g2, "public_email", "email", match_limit, max_checks)

    def get_followings_email(self, match_limit: int = 20, max_checks: int = DEFAULT_CONTACT_MAX_CHECKS) -> list:
        return self._contact_info(self.api.user_following_g2, "public_email", "email", match_limit, max_checks)

    def get_followers_phone(self, match_limit: int = 20, max_checks: int = DEFAULT_CONTACT_MAX_CHECKS) -> list:
        return self._contact_info(
            self.api.user_followers_g2, "contact_phone_number", "contact_phone_number", match_limit, max_checks
        )

    def get_followings_phone(self, match_limit: int = 20, max_checks: int = DEFAULT_CONTACT_MAX_CHECKS) -> list:
        return self._contact_info(
            self.api.user_following_g2, "contact_phone_number", "contact_phone_number", match_limit, max_checks
        )


def check_hiker_token(token: str) -> dict:
    """Verify a token by asking HikerAPI for its own balance.

    /sys/balance is free and needs nothing but the token, so this both proves
    the key works and tells the user what credit is left - the one thing they
    actually want to know right after pasting it. Raises HikerAPIError with
    HikerAPI's own message when the key is rejected.
    """
    client = AppClient(token=(token or "").strip())
    try:
        data = client._request("get", "/sys/balance")
    except Exception as e:
        raise HikerAPIError(str(e)) from e
    finally:
        client._client.close()
    if not isinstance(data, dict) or "requests" not in data:
        detail = (data or {}).get("detail") if isinstance(data, dict) else None
        raise HikerAPIError(str(detail or data)[:200])
    return {"requests": data["requests"], "amount": data.get("amount"), "currency": data.get("currency")}


def mask_token(token: Optional[str]) -> Optional[str]:
    """A token rendered so it can be recognised but not reused."""
    token = (token or "").strip()
    if not token:
        return None
    return f"{token[:4]}…{token[-4:]}" if len(token) > 12 else "…" * 3


def hiker_balance() -> Optional[dict]:
    """Remaining HikerAPI quota as {"requests", "amount", "currency"}, or None
    when HikerAPI isn't the backend in use. /sys/balance is free (HikerAPI
    doesn't bill it); the hikerapi client has no method for it, hence its
    generic _request."""
    if os.getenv("INSTAGRAM_BACKEND") == "instagrapi":
        return None
    token = resolve_hiker_token()
    if not token:
        return None
    client = AppClient(token=token)
    try:
        data = client._request("get", "/sys/balance")
    except Exception as e:
        raise HikerAPIError(f"balance lookup failed: {e}") from e
    finally:
        client._client.close()
    if not isinstance(data, dict) or "requests" not in data:
        raise HikerAPIError(f"unexpected /sys/balance response: {str(data)[:200]}")
    return {"requests": data["requests"], "amount": data.get("amount"), "currency": data.get("currency")}


def build_service(target: str, backend: Optional[str] = None) -> OsintgramService:
    """Construct an OsintgramService using the configured backend.

    `backend` is "hikerapi", "instagrapi", or None to auto-select (also
    overridable via the INSTAGRAM_BACKEND env var): prefer HikerAPI if a
    token is configured, otherwise fall back to instagrapi if a saved
    session exists.
    """
    backend = backend or os.getenv("INSTAGRAM_BACKEND")

    use_hikerapi = backend == "hikerapi" or (backend is None and resolve_hiker_token())
    if use_hikerapi:
        token = resolve_hiker_token()
        if not token:
            raise OsintServiceError(
                "HikerAPI selected but no token configured: set HIKERAPI_TOKEN or "
                "config/credentials.ini's [Credentials] hikerapi_token"
            )
        return OsintgramService(target, AppClient(token=token))

    if backend in ("instagrapi", None):
        from src.instagrapi_backend import (
            InstagrapiBackendError,
            InstagrapiClient,
            resolve_instagrapi_credentials,
            session_exists,
        )

        if not session_exists():
            raise OsintServiceError(
                "No backend configured: set HIKERAPI_TOKEN for HikerAPI, or run "
                "`python scripts/instagrapi_login.py` once to use instagrapi instead"
            )
        username, password = resolve_instagrapi_credentials()
        if not username or not password:
            raise OsintServiceError(
                "instagrapi session found but no username/password configured "
                "in config/credentials.ini's [Credentials] section"
            )
        try:
            return OsintgramService(target, InstagrapiClient(username, password))
        except InstagrapiBackendError as e:
            raise OsintServiceError(str(e)) from e

    raise OsintServiceError(f"Unknown INSTAGRAM_BACKEND: {backend!r} (expected hikerapi or instagrapi)")
