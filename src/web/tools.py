"""Tool-use definitions bound to one resolved OsintgramService, for a local
Ollama model's function-calling.

Every tool is a closure over an already-constructed `OsintgramService`, so
the Instagram target username is fixed before the model ever runs - the LLM
only ever supplies capability-specific parameters (a result limit, and
similar), never a username. This avoids the model inventing or mistyping an
account to look up.

Plain, undecorated functions with type hints and a Google-style docstring are
passed straight to `ollama.chat(tools=...)`, which generates each tool's JSON
schema from the signature/docstring itself - no manual schema needed.
"""
import inspect
import json
import typing
from typing import Literal, Optional

from src.osint_service import (
    DEFAULT_CONTACT_MAX_CHECKS,
    OsintgramService,
    OsintServiceError,
    QueryCancelledError,
)


def _to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


# Local models calling tools sometimes serialize numeric arguments as JSON
# strings (e.g. "100" instead of 100), or send a sentinel word like "all"/
# "none" instead of omitting an optional argument, even though the schema
# says integer - every int-typed parameter across these tools is one of
# these four names, so kwargs are coerced generically here rather than at
# each call site.
_INT_PARAMS = {"limit", "limit_posts", "match_limit", "max_checks"}
# Of those, only these are clamped to the UI's "Limite chiamate" ceiling -
# they bound how many *results* a tool returns/scans. max_checks is
# deliberately excluded: it used to be clamped here too, but that capped how
# many candidates got *examined* regardless of whether each one turned out
# to be a free cache hit or a real backend request, so a query that got
# lucky with cache hits still stopped scanning early for no real-cost
# reason. The actual real-request budget is now enforced once, centrally,
# in OsintgramService.api.max_calls (see src/web/app.py) - a cache hit never
# counts against it, and the scanning loops it backs return whatever
# partial results they already found instead of erroring out when it's
# reached (see _paginate/_contact_info in osint_service.py). max_checks
# keeps its own generous default (DEFAULT_CONTACT_MAX_CHECKS) purely as a
# safety ceiling against scanning a huge account forever when nothing but
# cache hits are being spent.
_CLAMPED_BY_MAX_ITEMS = {"limit", "limit_posts", "match_limit"}

# Searches that belong to no account: they run without a target username, so
# the web UI doesn't require one when only these are selected.
TARGET_FREE_TOOLS = {"search_hashtag", "search_location"}


def _coerce_int(value):
    if value is None or isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        # A non-numeric string ("all", "none", "unlimited", ...) means the
        # model meant "no limit" rather than a real value - every one of
        # these parameters already treats None as unlimited.
        return None


def resolve_call_args(fn, model_args: dict, max_items: Optional[int] = None) -> dict:
    """Compute the *effective* kwargs a tool call will run with.

    Resolves every parameter `fn` declares - filling in `fn`'s own default
    for anything the model omitted - then coerces and clamps the int-typed
    ones. The caller (src/web/app.py) uses this result both to actually
    invoke the tool and to show the tool_call event, so what's displayed to
    the user is what actually ran - not just what the model asked for, which
    can be misleading (e.g. the model sending "all" still gets capped, but a
    trace that only echoed "all" verbatim would look like the cap did
    nothing even though it did).
    """
    resolved = {}
    for name, param in inspect.signature(fn).parameters.items():
        if name in model_args:
            value = model_args[name]
        elif param.default is not inspect.Parameter.empty:
            value = param.default
        else:
            continue  # required param the model didn't supply - let the call fail naturally
        if name in _INT_PARAMS:
            value = _coerce_int(value)
            if max_items is not None and name in _CLAMPED_BY_MAX_ITEMS:
                value = max_items if value is None else min(value, max_items)
        resolved[name] = value
    return resolved


def _parse_docstring(fn) -> tuple:
    """Split a tool's Google-style docstring into (description, {param: text})."""
    doc = inspect.getdoc(fn) or ""
    summary, _, args_block = doc.partition("Args:")
    param_docs = {}
    current = None
    for line in args_block.splitlines():
        name, sep, text = line.strip().partition(":")
        if sep and name.isidentifier():
            current = name
            param_docs[current] = text.strip()
        elif current and line.strip():
            param_docs[current] += " " + line.strip()
    return " ".join(summary.split()), param_docs


def tool_specs() -> list:
    """Describe every tool and its parameters for the web UI's manual ("Base")
    mode, where the user picks commands and sets their parameters directly
    instead of letting the model choose.

    Derived from the very same functions handed to the model (signature +
    docstring), so both modes always expose the same commands with the same
    parameters and defaults. The closures only touch `service` when actually
    called, so building them against None just to introspect them is safe.
    """
    specs = []
    for fn in build_tools(None):
        description, param_docs = _parse_docstring(fn)
        params = []
        for name, param in inspect.signature(fn).parameters.items():
            spec = {
                "name": name,
                "type": "integer" if name in _INT_PARAMS else "string",
                "default": None if param.default is inspect.Parameter.empty else param.default,
                "description": param_docs.get(name, ""),
            }
            # A Literal[...] annotation becomes a fixed set of choices, so the
            # Base-mode form can render a dropdown instead of a free-text box.
            if typing.get_origin(param.annotation) is Literal:
                spec["choices"] = list(typing.get_args(param.annotation))
            params.append(spec)
        specs.append({
            "name": fn.__name__,
            "description": description,
            "params": params,
            "needs_target": fn.__name__ not in TARGET_FREE_TOOLS,
        })
    return specs


def build_tools(service: OsintgramService) -> list:
    """Return the tool functions available for `service`'s target."""

    def _call(fn, /, **kwargs) -> str:
        try:
            return _to_json(fn(**kwargs))
        except QueryCancelledError:
            raise  # unwind the whole run instead of becoming one tool's error
        except OsintServiceError as e:
            return _to_json({"error": str(e)})
        except Exception as e:  # keep one bad tool call from failing the whole turn
            return _to_json({"error": f"unexpected error: {e}"})

    def get_user_info() -> str:
        """Get profile info for the target: bio and bio links, follower/following/
        media counts, business/verified flags, account category, and any public
        contact or address field (email, phone, street, city, coordinates)
        Instagram exposes on the profile itself. Costs no extra request."""
        return _call(service.get_user_info)

    def get_account_about() -> str:
        """Get Instagram's "About this account" panel for the target: the country
        the account is registered in, the month it was created, and how many
        times its username changed. Use it to tell how old an account is or
        whether it was ever renamed - none of this is in get_user_info. Note
        Instagram reports only the *number* of username changes, never the old
        usernames themselves, and the creation date has no day, only a month
        and a year."""
        return _call(service.get_account_about)

    def get_followers(limit: Optional[int] = 200) -> str:
        """List the target's followers (id, username, full name).

        Args:
            limit: Maximum number of followers to return.
        """
        return _call(service.get_followers, limit=limit)

    def get_followings(limit: Optional[int] = 200) -> str:
        """List accounts the target follows (id, username, full name).

        Args:
            limit: Maximum number of followed accounts to return.
        """
        return _call(service.get_followings, limit=limit)

    def get_hashtags(limit_posts: Optional[int] = None) -> str:
        """Count hashtags used in the target's posts, most-used first.

        Args:
            limit_posts: Maximum number of recent posts to scan (omit for all).
        """
        return _call(service.get_hashtags, limit_posts=limit_posts)

    def get_addrs(limit_posts: Optional[int] = None) -> str:
        """Reverse-geocode the locations tagged on the target's posts into
        addresses, most recent first.

        Args:
            limit_posts: Maximum number of recent posts to scan (omit for all).
        """
        return _call(service.get_addrs, limit_posts=limit_posts)

    def get_captions(limit_posts: Optional[int] = None) -> str:
        """Get the text captions of the target's posts.

        Args:
            limit_posts: Maximum number of recent posts to scan (omit for all).
        """
        return _call(service.get_captions, limit_posts=limit_posts)

    def get_total_comments(limit_posts: Optional[int] = None) -> str:
        """Get total/min/max/average comment counts across the target's posts.

        Args:
            limit_posts: Maximum number of recent posts to scan (omit for all).
        """
        return _call(service.get_total_comments, limit_posts=limit_posts)

    def get_total_likes(limit_posts: Optional[int] = None) -> str:
        """Get total/min/max/average like counts across the target's posts.

        Args:
            limit_posts: Maximum number of recent posts to scan (omit for all).
        """
        return _call(service.get_total_likes, limit_posts=limit_posts)

    def get_media_type(limit_posts: Optional[int] = None) -> str:
        """Count how many of the target's posts are photos, videos and
        carousels (multi-photo/video posts), plus total/average video views
        and how many posts are collaborations or paid partnerships.

        Args:
            limit_posts: Maximum number of recent posts to scan (omit for all).
        """
        return _call(service.get_media_type, limit_posts=limit_posts)

    def get_posting_times(limit_posts: Optional[int] = None) -> str:
        """When the target usually posts: post counts per weekday and per
        hour (UTC), the most active day and hour, the first/last post date
        and the average number of days between posts.

        Args:
            limit_posts: Maximum number of recent posts to scan (omit for all).
        """
        return _call(service.get_posting_times, limit_posts=limit_posts)

    def get_photo_descriptions(limit_posts: Optional[int] = None) -> str:
        """Alt text (a written description of what a photo shows) of the
        target's photos, carousel photos included. Only available when the
        post's author wrote it, so most accounts have none: the result says
        how many photos were checked and how many have one.

        Args:
            limit_posts: Maximum number of recent posts to scan (omit for all).
        """
        return _call(service.get_photo_descriptions, limit_posts=limit_posts)

    def get_comment_data(limit_posts: Optional[int] = None) -> str:
        """Get every comment on the target's posts, with the commenter's
        username and which post it was on.

        Args:
            limit_posts: Maximum number of recent posts to scan (omit for all).
        """
        return _call(service.get_comment_data, limit_posts=limit_posts)

    def get_people_who_commented(limit_posts: Optional[int] = None) -> str:
        """List the accounts that commented on the target's posts, ranked by
        how many comments each one left.

        Args:
            limit_posts: Maximum number of recent posts to scan (omit for all).
        """
        return _call(service.get_people_who_commented, limit_posts=limit_posts)

    def get_people_who_tagged(limit: Optional[int] = None) -> str:
        """List the accounts that tagged the target in their own posts, ranked
        by how many times each one did.

        Args:
            limit: Maximum number of tagged posts to scan (omit for all).
        """
        return _call(service.get_people_who_tagged, limit=limit)

    def get_people_tagged_by_user(limit_posts: Optional[int] = None) -> str:
        """List the accounts the target tagged in their own posts, ranked by
        how many posts each one appears in.

        Args:
            limit_posts: Maximum number of recent posts to scan (omit for all).
        """
        return _call(service.get_people_tagged_by_user, limit_posts=limit_posts)

    def get_user_photos(limit: Optional[int] = None) -> str:
        """Get direct CDN URLs for the target's posted photos (no download,
        just the URLs and media ids).

        Args:
            limit: Maximum number of photos to return (omit for all).
        """
        return _call(service.get_user_photos, limit=limit)

    def get_user_propic() -> str:
        """Get the direct CDN URL of the target's profile picture (highest
        resolution available)."""
        return _call(service.get_user_propic)

    def get_user_stories() -> str:
        """Get direct CDN URLs for the target's currently active stories, if
        any (no download, just the URLs and media type)."""
        return _call(service.get_user_stories)

    def search_hashtag(hashtag: str = "", sort: Literal["top", "recent"] = "top",
                       limit: Optional[int] = 30) -> str:
        """Search Instagram for posts published with a hashtag, and who posted
        them. Does not need a target account.

        Args:
            hashtag: The hashtag to search for (with or without "#").
            sort: "top" for the most popular posts, "recent" for the newest.
            limit: Maximum number of posts to collect.
        """
        if not (hashtag or "").strip():
            return _to_json({"error": "Specify a hashtag to search for."})
        return _call(service.search_hashtag, hashtag=hashtag, sort=sort, limit=limit)

    def search_location(place: str = "", limit: Optional[int] = 30) -> str:
        """Search Instagram for recent posts published from a place (searched
        by name), and who posted them. Does not need a target account.

        Args:
            place: Name of the place, e.g. "Colosseo Roma".
            limit: Maximum number of posts to collect.
        """
        if not (place or "").strip():
            return _to_json({"error": "Specify a place to search for."})
        return _call(service.search_location, place=place, limit=limit)

    def get_highlights() -> str:
        """List the target's Story Highlights (archived stories pinned on the
        profile): title, number of stories, cover image and dates."""
        return _call(service.get_highlights)

    def get_suggested_profiles() -> str:
        """List the accounts Instagram suggests as related to the target
        ("Suggested for you") - often reveals the target's real circle or
        alternate accounts. HikerAPI backend only."""
        return _call(service.get_suggested_profiles)

    def compare_with(other_username: str = "", scope: Literal["both", "followers", "followings"] = "both",
                     limit: Optional[int] = 500) -> str:
        """Find connections in common between the target and another account:
        accounts that follow both, and accounts both of them follow.

        Args:
            other_username: The other public Instagram account to compare against.
            scope: Which side(s) to compare - "followers", "followings" or "both".
            limit: Max followers/followings to pull from each account.
        """
        if not (other_username or "").strip():
            return _to_json({"error": "Specify the other account to compare with (other_username)."})
        return _call(service.compare_with, other_username=other_username.strip(), scope=scope, limit=limit)

    def get_followers_email(match_limit: Optional[int] = 20, max_checks: Optional[int] = DEFAULT_CONTACT_MAX_CHECKS) -> str:
        """Find public email addresses among the target's followers.

        Args:
            match_limit: Maximum number of matches to return.
            max_checks: Advanced/internal - leave unset. Caps how many followers get individually checked before giving up.
        """
        return _call(service.get_followers_email, match_limit=match_limit, max_checks=max_checks)

    def get_followings_email(match_limit: Optional[int] = 20, max_checks: Optional[int] = DEFAULT_CONTACT_MAX_CHECKS) -> str:
        """Find public email addresses among accounts the target follows.

        Args:
            match_limit: Maximum number of matches to return.
            max_checks: Advanced/internal - leave unset. Caps how many accounts get individually checked before giving up.
        """
        return _call(service.get_followings_email, match_limit=match_limit, max_checks=max_checks)

    def get_followers_phone(match_limit: Optional[int] = 20, max_checks: Optional[int] = DEFAULT_CONTACT_MAX_CHECKS) -> str:
        """Find public phone numbers among the target's followers.

        Args:
            match_limit: Maximum number of matches to return.
            max_checks: Advanced/internal - leave unset. Caps how many followers get individually checked before giving up.
        """
        return _call(service.get_followers_phone, match_limit=match_limit, max_checks=max_checks)

    def get_followings_phone(match_limit: Optional[int] = 20, max_checks: Optional[int] = DEFAULT_CONTACT_MAX_CHECKS) -> str:
        """Find public phone numbers among accounts the target follows.

        Args:
            match_limit: Maximum number of matches to return.
            max_checks: Advanced/internal - leave unset. Caps how many accounts get individually checked before giving up.
        """
        return _call(service.get_followings_phone, match_limit=match_limit, max_checks=max_checks)

    return [
        get_user_info,
        get_account_about,
        get_followers,
        get_followings,
        get_hashtags,
        get_addrs,
        get_captions,
        get_total_comments,
        get_total_likes,
        get_media_type,
        get_posting_times,
        get_photo_descriptions,
        get_comment_data,
        get_people_who_commented,
        get_people_who_tagged,
        get_people_tagged_by_user,
        get_user_photos,
        get_user_propic,
        get_user_stories,
        get_highlights,
        get_suggested_profiles,
        get_followers_email,
        get_followings_email,
        get_followers_phone,
        get_followings_phone,
        compare_with,
        search_hashtag,
        search_location,
    ]
