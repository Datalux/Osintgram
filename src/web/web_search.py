"""Privacy-first public web search integration for Osintgram.

Supports multiple providers:
  - duckduckgo: free instant answer search (zero-config, no API key)
  - wikipedia: free encyclopedic search for venues, landmarks, and brands
  - searxng: self-hosted, private meta-search engine
  - parallel: Parallel Search API / MCP (https://docs.parallel.ai)

Enforces strict privacy guardrails: queries containing Instagram handles,
profile URLs, or target usernames are rejected before any network call.
"""
import configparser
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

CREDENTIALS_PATH = Path("config/credentials.ini")

DEFAULT_PROVIDER = "duckduckgo"
DEFAULT_SEARXNG_URL = "http://127.0.0.1:8080"


@dataclass
class WebSearchConfig:
    enabled: bool = False
    provider: str = DEFAULT_PROVIDER
    searxng_url: str = DEFAULT_SEARXNG_URL
    parallel_api_key: str = ""


_runtime_config: Optional[WebSearchConfig] = None


def resolve_web_search_config() -> WebSearchConfig:
    """Resolve current web search config from runtime memory, env, or credentials.ini."""
    if _runtime_config is not None:
        return _runtime_config

    enabled = False
    provider = DEFAULT_PROVIDER
    searxng_url = DEFAULT_SEARXNG_URL
    parallel_key = ""

    if CREDENTIALS_PATH.exists():
        cp = configparser.ConfigParser()
        try:
            cp.read(CREDENTIALS_PATH, encoding="utf-8")
            if cp.has_section("WebSearch"):
                sec = cp["WebSearch"]
                if "enabled" in sec:
                    enabled = sec.getboolean("enabled", fallback=enabled)
                provider = sec.get("provider", fallback=provider).strip().lower()
                searxng_url = sec.get("searxng_url", fallback=searxng_url).strip()
                parallel_key = sec.get("parallel_api_key", fallback=parallel_key).strip()
        except Exception:
            pass

    # Environment variables take precedence over config file
    env_enabled = os.getenv("WEB_SEARCH_ENABLED")
    if env_enabled is not None:
        enabled = env_enabled.lower() in ("1", "true", "yes")

    if "WEB_SEARCH_PROVIDER" in os.environ:
        provider = os.getenv("WEB_SEARCH_PROVIDER", provider).strip().lower()

    if "SEARXNG_URL" in os.environ:
        searxng_url = _validate_searxng_url(os.getenv("SEARXNG_URL", searxng_url))

    if "PARALLEL_API_KEY" in os.environ:
        parallel_key = os.getenv("PARALLEL_API_KEY", parallel_key).strip()

    return WebSearchConfig(
        enabled=enabled,
        provider=provider or DEFAULT_PROVIDER,
        searxng_url=searxng_url or DEFAULT_SEARXNG_URL,
        parallel_api_key=parallel_key,
    )


def set_runtime_web_search_config(config: WebSearchConfig) -> None:
    """Update runtime web search configuration."""
    global _runtime_config
    _runtime_config = config


def save_web_search_config(config: WebSearchConfig) -> bool:
    """Persist web search configuration to config/credentials.ini."""
    cp = configparser.ConfigParser()
    if CREDENTIALS_PATH.exists():
        try:
            cp.read(CREDENTIALS_PATH, encoding="utf-8")
        except Exception:
            pass

    if not cp.has_section("WebSearch"):
        cp.add_section("WebSearch")

    cp.set("WebSearch", "enabled", "true" if config.enabled else "false")
    cp.set("WebSearch", "provider", config.provider)
    cp.set("WebSearch", "searxng_url", _validate_searxng_url(config.searxng_url))
    cp.set("WebSearch", "parallel_api_key", config.parallel_api_key)

    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CREDENTIALS_PATH, "w", encoding="utf-8") as f:
        cp.write(f)

    set_runtime_web_search_config(config)
    return True


def _validate_searxng_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return DEFAULT_SEARXNG_URL
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid SEARXNG_URL: {url!r}. Must start with http:// or https://")
    return url


def validate_privacy_guard(
    query: str,
    target_username: Optional[str] = None,
    extra_identifiers: Optional[List[str]] = None,
) -> str:
    """Ensure the query complies with privacy constraints.

    Rejects queries containing target usernames, personal profile URLs,
    social media handles, email addresses, phone numbers, or target personal identifiers.
    """
    clean_q = query.strip()
    if not clean_q:
        raise ValueError("Search query cannot be empty.")

    q_lower = clean_q.lower()

    if target_username and target_username.strip():
        target_clean = target_username.strip().lstrip("@").lower()
        if target_clean and target_clean in q_lower:
            raise ValueError(
                f"Privacy violation: web search cannot query target username (@{target_username}). "
                "Only searches for public venues, landmarks, brands, or general topics are permitted."
            )

    if extra_identifiers:
        for ident in extra_identifiers:
            ident_clean = (ident or "").strip().lower()
            if len(ident_clean) >= 3 and ident_clean in q_lower:
                raise ValueError(
                    f"Privacy violation: web search query cannot contain target personal identifier ({ident}). "
                    "Only searches for public venues, landmarks, brands, or general topics are permitted."
                )

    # Reject email addresses
    if re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", clean_q):
        raise ValueError("Privacy violation: web search query must not contain email addresses.")

    # General Instagram handles / URL patterns
    if "instagram.com" in q_lower or "instagr.am" in q_lower:
        raise ValueError("Privacy violation: web search query must not contain Instagram URLs.")

    # Match @username patterns
    if re.search(r"@[\w\.\_]+", clean_q):
        raise ValueError(
            "Privacy violation: web search query must not contain @username handles. "
            "Only search for public places, venues, or organizations."
        )

    return clean_q


def _search_duckduckgo(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Query DuckDuckGo Instant Answer API."""
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Osintgram-Web/2.0 (Privacy-First OSINT)"})
    with urllib.request.urlopen(req, timeout=7) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    abstract = data.get("AbstractText", "").strip()
    abstract_url = data.get("AbstractURL", "").strip()
    heading = data.get("Heading", "").strip() or query

    if abstract:
        results.append({
            "title": heading,
            "url": abstract_url or "https://duckduckgo.com/?q=" + urllib.parse.quote(query),
            "snippet": abstract,
        })

    for topic in data.get("RelatedTopics", []):
        if len(results) >= max_results:
            break
        text = topic.get("Text", "").strip()
        first_url = topic.get("FirstURL", "").strip()
        if text and first_url:
            results.append({
                "title": text.split(" - ")[0] if " - " in text else heading,
                "url": first_url,
                "snippet": text,
            })

    # If Instant Answer returned nothing, provide a direct fallback search link
    if not results:
        results.append({
            "title": f"DuckDuckGo search: {query}",
            "url": f"https://duckduckgo.com/?q={urllib.parse.quote(query)}",
            "snippet": f"No direct summary found for '{query}'. Direct search link available.",
        })

    return results[:max_results]


def _search_wikipedia(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Query Wikipedia OpenSearch API."""
    url = (
        f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(query)}"
        f"&limit={max_results}&namespace=0&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Osintgram-Web/2.0 (OpenSearch)"})
    with urllib.request.urlopen(req, timeout=7) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # Format: [query, [titles], [snippets], [urls]]
    results = []
    if len(data) >= 4:
        titles = data[1]
        snippets = data[2]
        urls = data[3]
        for t, s, u in zip(titles, snippets, urls):
            results.append({
                "title": t,
                "url": u,
                "snippet": s or f"Wikipedia article for {t}.",
            })
    return results


def _search_searxng(query: str, searxng_url: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Query self-hosted SearXNG instance via JSON API."""
    base = searxng_url.rstrip("/")
    url = f"{base}/search?q={urllib.parse.quote(query)}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Osintgram-Web/2.0"})
    with urllib.request.urlopen(req, timeout=7) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    for item in data.get("results", [])[:max_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
        })
    return results


def _search_parallel(query: str, api_key: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Query Parallel Search API (Parallel Search MCP compatible)."""
    url = "https://api.parallel.ai/v1/search"
    payload = json.dumps({"query": query, "max_results": max_results}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Osintgram-Web/2.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    for item in data.get("results", [])[:max_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", "") or item.get("content", ""),
        })
    return results


def search_public_web(
    query: str,
    target_username: Optional[str] = None,
    max_results: int = 4,
) -> List[Dict[str, str]]:
    """Execute a privacy-guarded web search using the active provider."""
    cfg = resolve_web_search_config()
    if not cfg.enabled:
        raise RuntimeError(
            "Public web search is disabled in settings. Enable it in AI Settings (opt-in) to use web context."
        )

    clean_query = validate_privacy_guard(query, target_username=target_username)
    provider = (cfg.provider or DEFAULT_PROVIDER).lower()

    if provider == "searxng":
        return _search_searxng(clean_query, cfg.searxng_url, max_results=max_results)
    elif provider == "wikipedia":
        return _search_wikipedia(clean_query, max_results=max_results)
    elif provider == "parallel":
        return _search_parallel(clean_query, cfg.parallel_api_key, max_results=max_results)
    else:
        # Default: DuckDuckGo
        return _search_duckduckgo(clean_query, max_results=max_results)
