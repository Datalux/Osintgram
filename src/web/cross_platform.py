"""Cross-Platform OSINT Pivot Scanner.

Discovers accounts across developer, social, blogging, and messaging networks
matching a given username without requiring external API keys.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT_SECS = 2.5
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


def _fetch(
    url: str, headers: Optional[dict] = None
) -> Tuple[int, bytes, Dict[str, str], Optional[str]]:
    """Fetch URL and return (status_code, body_bytes, headers_dict, error_msg)."""
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as resp:
            return resp.status, resp.read(), dict(resp.headers), None
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        return e.code, body, dict(e.headers), f"HTTP {e.code}"
    except Exception as e:
        return 0, b"", {}, str(e)


def _check_github(username: str) -> dict:
    quoted = urllib.parse.quote(username)
    status, body, _, err = _fetch(f"https://api.github.com/users/{quoted}")
    base = {
        "platform": "GitHub",
        "category": "Code & Development",
        "icon": "🐙",
        "url": f"https://github.com/{quoted}",
    }
    if status == 200:
        try:
            data = json.loads(body.decode("utf-8"))
            bio = (data.get("bio") or "").strip()
            name = (data.get("name") or "").strip()
            repos = data.get("public_repos", 0)
            details = []
            if name:
                details.append(name)
            if repos:
                details.append(f"{repos} repos")
            if bio:
                details.append(bio[:80])
            return {
                **base,
                "status": "found",
                "exists": True,
                "details": " · ".join(details) if details else "Active account",
            }
        except Exception:
            return {**base, "status": "found", "exists": True, "details": "Active profile"}
    elif status == 404:
        return {**base, "status": "not_found", "exists": False, "details": "Profile does not exist"}
    elif status in (403, 429):
        return {
            **base,
            "status": "error",
            "exists": False,
            "details": "Rate limit exceeded (unauthenticated GitHub API limit 60 req/h)",
        }
    return {
        **base,
        "status": "error",
        "exists": False,
        "details": f"Network error or timeout: {err or 'unreachable'}",
    }


def _check_gitlab(username: str) -> dict:
    quoted = urllib.parse.quote(username)
    status, body, _, err = _fetch(f"https://gitlab.com/api/v4/users?username={quoted}")
    base = {
        "platform": "GitLab",
        "category": "Code & Development",
        "icon": "🦊",
        "url": f"https://gitlab.com/{quoted}",
    }
    if status == 200:
        try:
            data = json.loads(body.decode("utf-8"))
            if isinstance(data, list) and len(data) > 0:
                matching = [u for u in data if u.get("username", "").lower() == username.lower()]
                if matching:
                    u = matching[0]
                    return {
                        **base,
                        "status": "found",
                        "exists": True,
                        "details": u.get("name") or "Active profile",
                    }
            return {**base, "status": "not_found", "exists": False, "details": "User not found"}
        except Exception:
            return {**base, "status": "error", "exists": False, "details": "Failed to parse API response"}
    elif status == 404:
        return {**base, "status": "not_found", "exists": False, "details": "User not found"}
    return {
        **base,
        "status": "error",
        "exists": False,
        "details": f"API error or timeout ({err or status})",
    }


def _check_telegram(username: str) -> dict:
    quoted = urllib.parse.quote(username)
    status, body, _, err = _fetch(f"https://t.me/{quoted}")
    base = {
        "platform": "Telegram",
        "category": "Messaging",
        "icon": "✈️",
        "url": f"https://t.me/{quoted}",
    }
    if status == 200:
        text = body.decode("utf-8", errors="ignore")
        if "tgme_page_extra" in text and "tgme_page_title" in text:
            m = re.search(r'<div class="tgme_page_title"[^>]*>(.*?)</div>', text, re.DOTALL)
            title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
            m_sub = re.search(r'<div class="tgme_page_extra"[^>]*>(.*?)</div>', text, re.DOTALL)
            sub = re.sub(r"<[^>]+>", "", m_sub.group(1)).strip() if m_sub else ""
            details = " · ".join(filter(None, [title, sub])) or "Active user / channel"
            return {**base, "status": "found", "exists": True, "details": details}
        return {
            **base,
            "status": "not_found",
            "exists": False,
            "details": "Telegram username not claimed",
        }
    elif status == 404:
        return {**base, "status": "not_found", "exists": False, "details": "User not found"}
    return {
        **base,
        "status": "error",
        "exists": False,
        "details": f"Network error or timeout ({err or status})",
    }


def _check_hackernews(username: str) -> dict:
    quoted = urllib.parse.quote(username)
    status, body, _, err = _fetch(f"https://hacker-news.firebaseio.com/v0/user/{quoted}.json")
    base = {
        "platform": "Hacker News",
        "category": "Tech Community",
        "icon": "🔶",
        "url": f"https://news.ycombinator.com/user?id={quoted}",
    }
    if status == 200:
        if body.strip() == b"null" or not body.strip():
            return {**base, "status": "not_found", "exists": False, "details": "Account not registered"}
        try:
            data = json.loads(body.decode("utf-8"))
            karma = data.get("karma", 0)
            return {**base, "status": "found", "exists": True, "details": f"{karma} karma"}
        except Exception:
            return {**base, "status": "error", "exists": False, "details": "Parse error"}
    elif status == 404:
        return {**base, "status": "not_found", "exists": False, "details": "Account not registered"}
    return {
        **base,
        "status": "error",
        "exists": False,
        "details": f"Network error or timeout ({err or status})",
    }


def _check_devto(username: str) -> dict:
    quoted = urllib.parse.quote(username)
    status, body, _, err = _fetch(f"https://dev.to/api/users/by_username?url={quoted}")
    base = {
        "platform": "Dev.to",
        "category": "Tech Community",
        "icon": "👩‍💻",
        "url": f"https://dev.to/{quoted}",
    }
    if status == 200:
        try:
            data = json.loads(body.decode("utf-8"))
            name = data.get("name", "")
            summary = data.get("summary", "")
            details = " · ".join(filter(None, [name, summary[:60]])) or "Author profile"
            return {**base, "status": "found", "exists": True, "details": details}
        except Exception:
            return {**base, "status": "found", "exists": True, "details": "Active profile"}
    elif status == 404:
        return {**base, "status": "not_found", "exists": False, "details": "Author not found"}
    return {
        **base,
        "status": "error",
        "exists": False,
        "details": f"Network error or timeout ({err or status})",
    }


def _check_dockerhub(username: str) -> dict:
    quoted = urllib.parse.quote(username)
    status, _, _, err = _fetch(f"https://hub.docker.com/v2/users/{quoted}/")
    base = {
        "platform": "Docker Hub",
        "category": "DevOps & Containers",
        "icon": "🐳",
        "url": f"https://hub.docker.com/u/{quoted}",
    }
    if status == 200:
        return {**base, "status": "found", "exists": True, "details": "Active namespace"}
    elif status == 404:
        return {**base, "status": "not_found", "exists": False, "details": "Namespace not found"}
    return {
        **base,
        "status": "error",
        "exists": False,
        "details": f"Network error or timeout ({err or status})",
    }


def _check_linktree(username: str) -> dict:
    quoted = urllib.parse.quote(username)
    status, body, _, err = _fetch(f"https://linktr.ee/{quoted}")
    base = {
        "platform": "Linktree",
        "category": "Bio Link & Social",
        "icon": "🌲",
        "url": f"https://linktr.ee/{quoted}",
    }
    if status == 200:
        text = body.decode("utf-8", errors="ignore")
        if (
            "page not found" in text.lower()
            or "profile not found" in text.lower()
            or "the page you are looking for" in text.lower()
        ):
            return {**base, "status": "not_found", "exists": False, "details": "Landing page not found"}
        return {**base, "status": "found", "exists": True, "details": "Active landing page"}
    elif status == 404:
        return {**base, "status": "not_found", "exists": False, "details": "Landing page not found"}
    return {
        **base,
        "status": "error",
        "exists": False,
        "details": f"Network error or timeout ({err or status})",
    }


def _check_gravatar(username: str) -> dict:
    quoted = urllib.parse.quote(username)
    status, body, _, err = _fetch(f"https://en.gravatar.com/{quoted}.json")
    base = {
        "platform": "Gravatar",
        "category": "Identity & Avatars",
        "icon": "👤",
        "url": f"https://en.gravatar.com/{quoted}",
    }
    if status == 200:
        try:
            data = json.loads(body.decode("utf-8"))
            entry = (data.get("entry") or [{}])[0]
            display_name = entry.get("displayName") or entry.get("preferredUsername") or ""
            about = (entry.get("aboutMe") or "").strip()
            details = " · ".join(filter(None, [display_name, about[:60]])) or "Registered profile"
            return {**base, "status": "found", "exists": True, "details": details}
        except Exception:
            return {**base, "status": "found", "exists": True, "details": "Registered profile"}
    elif status == 404:
        return {**base, "status": "not_found", "exists": False, "details": "Profile not registered"}
    return {
        **base,
        "status": "error",
        "exists": False,
        "details": f"Network error or timeout ({err or status})",
    }


def _check_pinterest(username: str) -> dict:
    quoted = urllib.parse.quote(username)
    status, body, _, err = _fetch(f"https://www.pinterest.com/{quoted}/")
    base = {
        "platform": "Pinterest",
        "category": "Visual & Social",
        "icon": "📌",
        "url": f"https://www.pinterest.com/{quoted}/",
    }
    if status == 200:
        text = body.decode("utf-8", errors="ignore")
        if (
            'content="404"' in text
            or "user not found" in text.lower()
            or "page not found" in text.lower()
        ):
            return {**base, "status": "not_found", "exists": False, "details": "Board / user not found"}
        return {**base, "status": "found", "exists": True, "details": "Active board / profile"}
    elif status == 404:
        return {**base, "status": "not_found", "exists": False, "details": "Board / user not found"}
    return {
        **base,
        "status": "error",
        "exists": False,
        "details": f"Network error or timeout ({err or status})",
    }


ALL_CHECKERS = [
    _check_github,
    _check_gitlab,
    _check_telegram,
    _check_hackernews,
    _check_devto,
    _check_dockerhub,
    _check_linktree,
    _check_gravatar,
    _check_pinterest,
]


def scan_cross_platform(username: str) -> dict:
    """Scan all supported platforms concurrently for matching username accounts."""
    clean_user = (username or "").strip().lstrip("@")
    if not clean_user:
        return {
            "target": "",
            "found_count": 0,
            "error_count": 0,
            "total_checked": 0,
            "platforms": [],
            "summary": "No username provided.",
        }

    # Strict username format validation to prevent injection or invalid requests
    if not USERNAME_PATTERN.match(clean_user):
        return {
            "target": clean_user,
            "error": (
                f"Invalid username '{clean_user}'. Username must contain only 1-40 alphanumeric "
                "characters, dots, underscores, or dashes."
            ),
            "found_count": 0,
            "error_count": 0,
            "total_checked": len(ALL_CHECKERS),
            "platforms": [],
            "summary": f"Invalid username format: '{clean_user}'",
        }

    results: List[dict] = []
    with ThreadPoolExecutor(max_workers=min(len(ALL_CHECKERS), 8)) as executor:
        futures = {executor.submit(checker, clean_user): checker.__name__ for checker in ALL_CHECKERS}
        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception as e:
                pass

    found = [p for p in results if p.get("status") == "found"]
    errors = [p for p in results if p.get("status") == "error"]
    not_found = [p for p in results if p.get("status") == "not_found"]

    # Order: found first, then errors (with explanations), then not found
    found.sort(key=lambda m: m["platform"])
    errors.sort(key=lambda m: m["platform"])
    not_found.sort(key=lambda m: m["platform"])
    ordered_platforms = found + errors + not_found

    summary_parts = [f"Found {len(found)} matching profile{'s' if len(found) != 1 else ''}"]
    if errors:
        summary_parts.append(f"{len(errors)} error{'s' if len(errors) != 1 else ''} / rate-limited")
    summary = (
        f"{', '.join(summary_parts)} across {len(ALL_CHECKERS)} checked platforms for @{clean_user}"
        if (found or errors) else
        f"No matching public profiles found across {len(ALL_CHECKERS)} platforms for @{clean_user}"
    )

    return {
        "target": clean_user,
        "found_count": len(found),
        "error_count": len(errors),
        "total_checked": len(ALL_CHECKERS),
        "summary": summary,
        "platforms": ordered_platforms,
    }
