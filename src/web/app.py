"""Local web UI: natural-language OSINT queries answered via a local Ollama
model's tool-calling over an Instagram data backend (HikerAPI or instagrapi) -
or, in manual ("Base") mode, the same tools picked and parameterized directly
by the user (/api/tools + /api/run), with no model involved.

Runs on 127.0.0.1 for personal local use, with no authentication layer - do
not change the bind host or expose this beyond localhost without adding auth
first. Uses a local LLM (Ollama) instead of a paid API so no external LLM
key/billing is required - only Ollama running locally with a tool-calling
capable model pulled (see README).
"""
import configparser
import inspect
import json
import os
import queue
import re
import threading
import time
import uuid
from contextlib import contextmanager
from importlib import metadata
from pathlib import Path
from typing import Callable, Iterator, Optional

import httpx

try:
    import ollama
except ImportError:
    ollama = None

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src import artwork
from src.osint_service import (
    OsintgramService,
    OsintServiceError,
    QueryCancelledError,
    TargetNotFoundError,
    build_service,
    check_hiker_token,
    hiker_balance,
    hiker_token_source,
    mask_token,
    resolve_hiker_token,
    save_hiker_token,
    set_runtime_hiker_token,
)
from src.web import cost, dossier, download, history
from src.web.request_cache import PersistentRequestCache
from src.web.tools import (
    TARGET_FREE_TOOLS,
    build_tools,
    resolve_call_args,
    tool_specs,
    tools_to_openai_specs,
)
from src.web.llm_client import (
    fetch_available_models,
    resolve_llm_info,
    run_llm_chat,
    save_ai_config,
    set_runtime_ai_config,
)

LLM_BACKEND = os.getenv("LLM_BACKEND", "auto").lower()
LMSTUDIO_API_KEY = os.getenv("LMSTUDIO_API_KEY", os.getenv("OPENAI_API_KEY", "lm-studio"))


def _detect_wsl_host() -> Optional[str]:
    try:
        with open("/proc/version", "r") as f:
            if "microsoft" in f.read().lower():
                import subprocess
                out = subprocess.check_output(["ip", "route"], text=True)
                for line in out.splitlines():
                    if line.startswith("default via"):
                        return line.split()[2]
    except Exception:
        pass
    return None


def resolve_lmstudio_host() -> str:
    return resolve_llm_info().get("base_url", "http://127.0.0.1:1234/v1")


def resolve_lmstudio_model(host: Optional[str] = None) -> str:
    return resolve_llm_info().get("model", "local-model")


def resolve_llm_backend() -> str:
    """Determine whether to use 'lmstudio' (OpenAI-compatible) or 'ollama'."""
    return resolve_llm_info().get("provider", "ollama")


OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or "llama3.1:8b"
OLLAMA_MAX_TOKENS = int(os.getenv("OLLAMA_MAX_TOKENS", "1024"))
# Ollama loads a model with a 4096-token window unless told otherwise, however
# large a context the model itself supports. That is not enough here: the 28
# tool schemas plus the system prompt are already ~2k tokens before a single
# result comes back, so two tool calls overflow the window - and Ollama drops
# the *oldest* tokens, which are exactly the system prompt and the tool
# definitions. The model then looks incompetent (forgets its instructions,
# stops calling tools) when it simply can no longer see them. Raise it, at the
# cost of some KV-cache memory: ~2 GB for an 8B model at 16k.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
# Picking the right tool is a decision, not a creative act. Ollama's default
# (0.8) makes an 8B model wander between plausible-looking tools and invent
# argument values; near-zero makes the choice repeatable.
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))

MAX_TOOL_TURNS = 8
# Every ollama.chat() call re-sends and reprocesses the full message history
# (no server-side prompt caching like the Anthropic API) - a large tool
# result left in that history gets re-processed on every subsequent turn of
# the same query. Cap what goes back into the model's context; the full,
# untruncated result is still shown to the user via the tool_result event.
MAX_ITEMS_FOR_MODEL = 15
MAX_CHARS_FOR_MODEL = 4000
# Result keys meant only for the web UI (e.g. the post preview grid's
# thumbnail URLs, see OsintgramService._post_preview) - dropped from what the
# model sees: useless to it, and they'd eat most of MAX_CHARS_FOR_MODEL.
UI_ONLY_RESULT_KEYS = {"previews", "timestamps"}
STATIC_DIR = Path(__file__).parent / "static"

# HikerAPI/instagrapi requests are the real cost/quota bottleneck (unlike
# Ollama, which is local and free). Caching lives at the individual-request
# level, not per tool call: OsintgramService.api.cache_store (wired below)
# caches one entry per raw Hiker/instagrapi request (e.g. a single
# user_by_id_v2(pk) lookup), shared across every target/query/tool in the
# process for as long as this dict lives - so if the same underlying request
# (same method+arguments) is needed again by *any* tool call, in *any*
# query, it's served without spending a real request again, as long as it's
# still within its TTL. Deliberately no separate whole-tool-result cache
# on top of this: that would only help when a tool got called again with
# the exact same arguments, and couldn't share a hit between two different
# tools (or two different queries) that both happen to need the same single
# underlying request. Persisted on disk (see src/web/request_cache.py) so
# cached responses survive restarts of the tool instead of being paid for
# again; set HIKER_CACHE_PATH to an empty string for a process-lifetime,
# in-memory cache instead. This TTL is just the fallback default (used when a
# request doesn't say otherwise) - the web UI's "Durata cache" control sends
# its own value with every request (see QueryRequest.cache_ttl_seconds), so
# it takes effect immediately with no server restart. Set HIKER_CACHE_TTL=0
# to disable caching by default.
DEFAULT_CACHE_TTL_SECONDS = int(os.getenv("HIKER_CACHE_TTL", "300"))
CACHE_PATH = os.getenv("HIKER_CACHE_PATH", "cache/requests.sqlite3")
_RAW_CALL_CACHE = PersistentRequestCache(Path(CACHE_PATH)) if CACHE_PATH else {}


def _resolve_ttl(ttl_seconds: Optional[int]) -> int:
    return DEFAULT_CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds


def _sanitize_unicode(value):
    """Neutralize unpaired UTF-16 surrogates found in real Instagram data
    (broken/truncated emoji in bios, captions, comments...) so nothing built
    from `value` can ever fail to UTF-8-encode later on. A lone surrogate
    survives `json.dumps(..., ensure_ascii=False)` untouched (json.loads is
    lenient about them), then blows up with UnicodeEncodeError the moment
    Starlette/FastAPI encodes the response body to bytes - for the SSE
    stream that happens mid-response, silently truncating the connection
    with no client-visible error and no further events (so counters that
    depend on a later event, like OK/KO/cache, freeze at whatever they were
    before the bad string)."""
    if isinstance(value, str):
        return value.encode("utf-8", "replace").decode("utf-8")
    if isinstance(value, dict):
        return {k: _sanitize_unicode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_unicode(v) for v in value]
    return value


def _run_tool_call(name: str, args: dict, fn) -> str:
    """Run a tool by name. Caching lives one level down, on individual
    Hiker/instagrapi requests (OsintgramService.api.cache_store) - not here.
    A whole tool call is never itself cached: two different tools (or the
    same tool with different arguments) that happen to need the same
    underlying user/page get to share that cache hit, which a whole-tool
    cache keyed on (tool, arguments) could never do."""
    if not fn:
        return json.dumps({"error": f"unknown tool {name}"})
    # Check the arguments against the signature first, so only a missing or
    # unexpected argument is handed back to the model (which can then retry).
    # A TypeError raised inside the tool is a bug and must not be mislabelled
    # as bad arguments, so the call itself is not wrapped.
    try:
        inspect.signature(fn).bind(**args)
    except TypeError as e:
        return json.dumps({"error": f"Invalid tool arguments for {name}: {e}"})
    return fn(**args)


app = FastAPI(title="Osintgram Web")

# The app is meant for 127.0.0.1 and has no login, which is fine for a tool
# you run on your own machine - but "local" is exactly what a DNS-rebinding
# page targets: it makes your browser resolve its own hostname to 127.0.0.1
# and then talks to this server as if it were same-origin. A state-changing
# endpoint with a JSON body is covered on its own, since a cross-origin JSON
# POST/DELETE needs a CORS preflight that never succeeds here - but a plain
# GET is a CORS "simple request": no preflight, no body, sent (and acted on
# server-side) whether or not the calling page can read the response. So any
# endpoint reachable by GET needs this check explicitly too, not just the
# ones that write. Used on the key and dossier endpoints; a JSON-body POST
# elsewhere doesn't strictly need it, but calling it is always harmless.
# Localhost only, a few lines.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1", "0.0.0.0"}


def _is_local_host(value: str) -> bool:
    host = (value or "").strip().lower()
    if host.startswith("http://") or host.startswith("https://"):
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0]
    # Strip the port, but not the colons of a bracketed IPv6 literal.
    if not host.startswith("[") and host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    elif host.startswith("["):
        host = host.split("]", 1)[0] + "]"
    return host in _LOCAL_HOSTS


def _require_local_origin(request: Request) -> None:
    if not _is_local_host(request.headers.get("host", "")):
        raise HTTPException(403, "This endpoint only answers requests reached via localhost.")
    origin = request.headers.get("origin")
    if origin and not _is_local_host(origin):
        raise HTTPException(403, "Origin not allowed.")


TOOL_SPECS = tool_specs()
TOOL_NAMES = {spec["name"] for spec in TOOL_SPECS}
# The tool callables, for signature introspection only (resolving a call's
# effective arguments when estimating its cost). Their closures only touch a
# service when actually invoked, so building them against None is safe.
_TOOL_FUNCS = {fn.__name__: fn for fn in build_tools(None)}


class _BaseRequest(BaseModel):
    # Optional: hashtag/place searches belong to no account (see
    # TARGET_FREE_TOOLS), so they run without one.
    target: Optional[str] = None
    verbose: bool = False
    max_items: Optional[int] = None
    cache_ttl_seconds: Optional[int] = None
    # Client-generated id for this run, so "Ferma" can cancel it server-side
    # (see /api/cancel). Optional: without it the run simply can't be stopped.
    run_id: Optional[str] = None


class CancelRequest(BaseModel):
    run_id: str


# run_id -> flag the worker checks before every real backend request. Entries
# live only for the duration of a run.
_CANCELLATIONS: dict = {}
_CANCELLATIONS_LOCK = threading.Lock()


@contextmanager
def _cancellation(run_id: Optional[str]):
    """Register a cancel flag for this run and always clean it up."""
    event = threading.Event()
    if run_id:
        with _CANCELLATIONS_LOCK:
            _CANCELLATIONS[run_id] = event
    try:
        yield event
    finally:
        if run_id:
            with _CANCELLATIONS_LOCK:
                _CANCELLATIONS.pop(run_id, None)


class QueryRequest(_BaseRequest):
    message: str


class ToolCallRequest(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


class RunRequest(_BaseRequest):
    """Manual ("Base") mode: the user picks the tools and their parameters
    directly - no model involved. Each call's `args` go through the same
    resolve_call_args as a model's, so omitted params get the tool's default,
    "all"/null means no limit, and "Limite chiamate" still clamps them."""
    calls: list[ToolCallRequest]


class QueryResponse(BaseModel):
    target: Optional[str] = None
    target_id: Optional[int] = None
    backend: str
    api_calls_total: int
    answer: str
    tool_calls: list


def _truncate_for_model(value) -> str:
    """Shrink a tool result before it re-enters the conversation history.

    The full, untruncated result is still emitted in the tool_result event
    (shown to the user) - this only caps what gets re-sent to Ollama, since
    that's what gets reprocessed in full on every subsequent turn.
    """
    if isinstance(value, dict):
        value = {k: v for k, v in value.items() if k not in UI_ONLY_RESULT_KEYS}
    if isinstance(value, list) and len(value) > MAX_ITEMS_FOR_MODEL:
        total = len(value)
        value = value[:MAX_ITEMS_FOR_MODEL]
        suffix = (
            f"\n[showing {MAX_ITEMS_FOR_MODEL} of {total} results - the full "
            "list was already shown to the user; do not re-fetch it just to "
            "see more]"
        )
    else:
        suffix = ""
    text = json.dumps(value, ensure_ascii=False, default=str) + suffix
    if len(text) > MAX_CHARS_FOR_MODEL:
        text = text[:MAX_CHARS_FOR_MODEL] + "... [truncated]"
    return text


def _describe_api_call(method: str, args: tuple, kwargs: dict) -> str:
    """Best-effort human-readable identifier for one backend request.

    Without this, a run of get_followers_email shows up in the verbose log
    as N identical "user_by_id_v2" lines with no way to tell them apart. All
    of OsintgramService's backend calls pass the "subject" (a username, a
    user pk, a media id) as the first positional argument and, for paginated
    ones, a page_id keyword - so a generic label on that first argument plus
    the page cursor covers every call site without per-method special-casing.
    """
    parts = []
    if args:
        if "username" in method:
            label = "username"
        elif "by_id" in method:
            label = "id"
        elif "media" in method:
            label = "media_id"
        else:
            label = "user_id"
        parts.append(f"{label}={args[0]}")
    page_id = kwargs.get("page_id") or kwargs.get("next_page_id")
    if page_id:
        parts.append(f"page={page_id}")
    return ", ".join(parts)


def _run_agent_events(
    service: OsintgramService,
    user_message: str,
    max_items: Optional[int] = None,
    cache_ttl_seconds: Optional[int] = None,
    emit_live: Optional[Callable[[dict], None]] = None,
):
    """Yield progress events as the agent works.

    Each event is one of:
    - {"type": "start", "target": ..., "target_id": ..., "backend": ...}    - once, first
    - {"type": "tool_call", "name": ..., "input": ...}                     - before running a tool
    - {"type": "api_call", "method": ..., "total": ..., "status": ...}     - one backend request attempt, live
      (status is "ok", "error", "retry", "cached" or "limit" - "cached" means
      it was served from the per-raw-request cache below without actually
      reaching the backend, so "total"/api_calls_total is unchanged for it;
      "retry" is a spent-but-not-final attempt, another one follows;
      "limit" is a request skipped because the query budget ran out)
    - {"type": "tool_result", "name": ..., "result": ..., "elapsed_ms": ...} - after it returns
    - {"type": "answer_delta", "text": ...}   - a piece of the answer, as the model writes it
    - {"type": "answer", "text": ...}         - the whole answer, once complete

    A generator so both the plain (blocking) and verbose (streamed) response
    modes share one implementation instead of duplicating the agent loop.

    `max_items` is the user-set ceiling from the web UI's quick-limit
    checkboxes, enforced on every tool call regardless of what the model asks
    for - see build_tools().

    `cache_ttl_seconds` overrides DEFAULT_CACHE_TTL_SECONDS for every
    individual backend request this query makes (service.api.cache_store/
    cache_ttl_seconds, checked before each raw call regardless of which tool
    triggers it) - the web UI's "Durata cache" control. There is no
    tool-level cache on top of this - a tool call always actually runs; only
    the raw requests underneath it may be served from cache.

    `emit_live`, if given, is called synchronously the instant each request
    actually reaches the backend client (see OsintgramService.api.on_call) -
    a single tool call can make many of these (pagination, one request per
    follower checked for contact info), all inside one blocking call this
    generator can't yield in the middle of; the caller (_run_safe_events)
    relays these through a queue from a worker thread so the API-call counter
    updates live instead of only once per tool call.

    `max_items` also becomes a hard ceiling on real (non-cached) backend
    requests for the whole query (service.api.max_calls) - not just on each
    tool's own result/scan size as resolve_call_args already does. That
    per-parameter clamping alone doesn't guarantee a query-wide total: it's
    applied independently to each tool call (so N tool calls could still add
    up to N times the limit), and it doesn't cover requests outside the
    clamped parameter (e.g. paging through a follower list before checking
    any of them). The cap here is enforced in one place for every request
    regardless of which tool or how many tool calls made it, and a cache hit
    never counts against it since nothing was actually sent to the backend
    for it.
    """
    yield _start_event(service, max_items, cache_ttl_seconds)

    tools = build_tools(service)
    from src.web.web_search import resolve_web_search_config
    web_enabled = resolve_web_search_config().enabled
    if not web_enabled:
        tools = [fn for fn in tools if fn.__name__ != "search_public_context"]
    if not service.target:
        # Without a target only the account-free searches can run at all -
        # offering the model the other twenty-odd tools would just buy a round
        # of calls that every one of them refuses.
        tools = [fn for fn in tools if fn.__name__ in TARGET_FREE_TOOLS or (fn.__name__ == "search_public_context" and web_enabled)]
    dispatch = {fn.__name__: fn for fn in tools}

    subject = (
        f"investigating the Instagram account @{service.target} (already "
        "resolved - do not attempt to look up a different username)"
        if service.target else
        "searching Instagram by hashtag, by place, or pulling the comments off "
        "one specific post/reel given its URL. No target account is set, so "
        "only those target-free tools are available - if the user asks about "
        "a specific account's own feed/followers/profile, say that they have "
        "to type the username in the target field first"
    )
    known = _profile_facts(service)
    system_prompt = (
        f"You are an OSINT assistant {subject}. "
        f"{known}"
        "Use the available tools to answer the user's "
        "request. Respond in the same language the user wrote in. If a tool "
        "result contains an \"error\" field, quote that error message to the "
        "user plainly - do not guess what it means, do not invent data, and "
        "do not claim you retried or will retry unless you actually call the "
        "tool again. Never write a tool call as plain text - always use the "
        "tool-calling mechanism. Tool parameters like a result limit are "
        "optional - only set one when the user's request names a specific "
        "number (or explicitly says \"all\"/\"everything\"); otherwise omit "
        "the parameter entirely instead of guessing a number. Minimize tool "
        "calls: get_user_info already includes follower_count, "
        "following_count and media_count, so use it for questions about "
        "those numbers instead of fetching the full list with "
        "get_followers/get_followings, which is slower and only needed when "
        "the user wants the actual accounts, not a count. "
        # Money, not just latency: these spend one request per account they
        # look at, so the model must not reach for them casually.
        "get_followers_email, get_followings_email, get_followers_phone and "
        "get_followings_phone are far more expensive than every other tool - "
        "each one spends a paid request per account it checks, hundreds in "
        "total. Call them only when the user explicitly asks for emails or "
        "phone numbers, never to satisfy a general question. "
        "Keep your final answer concise - summarize, don't repeat raw data "
        "verbatim the user can already see."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    backend = resolve_llm_backend()

    for _ in range(MAX_TOOL_TURNS):
        # Streamed so the final answer appears word by word instead of after a
        # silence: on a local 8B model writing a paragraph takes seconds, and
        # a frozen page reads as a hung tool. Tool calls arrive whole in their
        # own chunks, so they are simply collected until the turn ends.
        llm_info = resolve_llm_info()
        chat_gen = run_llm_chat(
            provider=llm_info["provider"],
            model=llm_info["model"],
            messages=messages,
            tools=tools,
            options={
                "num_predict": OLLAMA_MAX_TOKENS,
                "num_ctx": OLLAMA_NUM_CTX,
                "temperature": OLLAMA_TEMPERATURE,
            },
            lmstudio_url=llm_info.get("base_url", "http://127.0.0.1:1234/v1"),
            api_key=llm_info.get("api_key", ""),
        )
        content = ""
        tool_calls = []
        try:
            while True:
                delta_event = next(chat_gen)
                yield delta_event
        except StopIteration as stop:
            if stop.value:
                content, tool_calls = stop.value

        msg = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        messages.append(msg)

        if not tool_calls:
            yield {"type": "answer", "text": content}
            return

        for call in tool_calls:
            if hasattr(call, "function") and hasattr(call.function, "name"):
                name = call.function.name
                args = call.function.arguments
                call_id = getattr(call, "id", f"call_{name}")
            elif isinstance(call, dict):
                name = call.get("name") or (call.get("function") or {}).get("name")
                args = call.get("arguments") or (call.get("function") or {}).get("arguments") or {}
                call_id = call.get("id") or f"call_{name}"
            else:
                name = getattr(call, "name", "")
                args = getattr(call, "arguments", {})
                call_id = getattr(call, "id", f"call_{name}")

            result, parsed_result, is_error = yield from _execute_tool_events(
                service, name, dispatch.get(name), dict(args or {}), max_items, emit_live
            )
            model_facing_result = result if is_error else _truncate_for_model(parsed_result)
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "tool_name": name,
                "name": name,
                "content": model_facing_result,
            })

    # The loop ran out of turns with the model still asking for tools. Say so
    # plainly: the results it did collect are on screen either way.
    yield {
        "type": "answer",
        "text": (
            f"I ran out of steps ({MAX_TOOL_TURNS}) before finishing the request. "
            "The results collected so far are below — try asking something more "
            "specific, or pick the commands yourself in Base mode."
        ),
    }


def _profile_facts(service: OsintgramService) -> str:
    """What we already know about the target, for the system prompt.

    build_service resolves the profile before the agent ever runs, so these
    numbers are already paid for. Handing them to the model saves it a
    get_user_info round-trip for the questions people ask most ("how many
    followers?"), and stops it reaching for public-only tools on a private
    account. Returns "" when there is no target.
    """
    user = getattr(service, "user", None) or {}
    if not user:
        return ""
    bits = []
    for key, label in (("follower_count", "followers"), ("following_count", "following"),
                       ("media_count", "posts")):
        if isinstance(user.get(key), int):
            bits.append(f"{user[key]} {label}")
    if user.get("is_private"):
        if service.backend_name == "instagrapi":
            bits.append("the profile is PRIVATE on Instagram (call tools normally; if the logged-in user has permission or follows it, Instagram will return the data)")
        else:
            bits.append("the profile is PRIVATE, so any tool needing a public one will refuse")
    else:
        bits.append("the profile is public")
    for key in ("is_verified", "is_business"):
        if user.get(key):
            bits.append(key.replace("is_", "").replace("_", " "))
    if user.get("category_name") or user.get("category"):
        bits.append(f"category: {user.get('category_name') or user['category']}")
    if not bits:
        return ""
    return (
        "Already known about this account, at no further cost - use these "
        f"instead of calling a tool to get them: {'; '.join(bits)}. "
    )


def _run_direct_events(
    service: OsintgramService,
    calls: list,
    max_items: Optional[int] = None,
    cache_ttl_seconds: Optional[int] = None,
    emit_live: Optional[Callable[[dict], None]] = None,
):
    """Manual ("Base") mode counterpart of _run_agent_events: run exactly the
    tools the user picked, in order, with the parameters they set - no model
    involved, so no "answer" event. Emits the same start/tool_call/api_call/
    tool_result events, so the frontend's live log, counters and result cards
    work unchanged in both modes."""
    yield _start_event(service, max_items, cache_ttl_seconds)

    dispatch = {fn.__name__: fn for fn in build_tools(service)}
    for call in calls:
        yield from _execute_tool_events(service, call.name, dispatch.get(call.name), call.args, max_items, emit_live)


def _start_event(service: OsintgramService, max_items: Optional[int], cache_ttl_seconds: Optional[int]) -> dict:
    """Wire the per-request cache/budget onto `service` for this query (see
    _run_agent_events for what each one means) and return the "start" event."""
    service.api.cache_store = _RAW_CALL_CACHE
    service.api.cache_ttl_seconds = _resolve_ttl(cache_ttl_seconds)
    service.api.max_calls = max_items
    return {
        "type": "start",
        "target": service.target,
        "target_id": service.target_id,
        "backend": service.backend_name,
        "api_calls_total": service.api_call_count,
    }


def _execute_tool_events(
    service: OsintgramService,
    name: str,
    fn,
    raw_args: dict,
    max_items: Optional[int],
    emit_live: Optional[Callable[[dict], None]],
):
    """Run one tool call, yielding its "tool_call" and "tool_result" events
    (plus live "api_call" ones via `emit_live`). Shared by both the AI and the
    manual mode. Returns (raw JSON result, parsed result, is_error) to the
    caller via `yield from`."""
    # Resolve to the *effective* args (given value, or the tool's own
    # default if omitted, coerced and clamped to max_items) before
    # showing or using them - otherwise the trace can show something
    # like "all" even though it was actually capped, which looks like
    # the cap did nothing.
    args = resolve_call_args(fn, raw_args, max_items) if fn else raw_args
    yield {"type": "tool_call", "name": name, "input": args}

    api_calls_before = service.api_call_count
    if emit_live:
        service.api.on_call = lambda method, total, cargs, ckwargs, status, error: emit_live(
            {
                "type": "api_call",
                "method": method,
                "total": total,
                "detail": _describe_api_call(method, cargs, ckwargs),
                "status": status,
                "error": error,
            }
        )
    started = time.monotonic()
    try:
        result = _run_tool_call(name, args, fn)
    finally:
        if emit_live:
            service.api.on_call = None
    elapsed_ms = round((time.monotonic() - started) * 1000)
    api_calls_total = service.api_call_count
    try:
        parsed_result = _sanitize_unicode(json.loads(result))
    except (TypeError, ValueError):
        parsed_result = result
    is_error = isinstance(parsed_result, dict) and "error" in parsed_result
    tool_event = {
        "type": "tool_result",
        "name": name,
        "result": parsed_result,
        "is_error": is_error,
        "elapsed_ms": elapsed_ms,
        "api_calls_delta": api_calls_total - api_calls_before,
        "api_calls_total": api_calls_total,
    }
    if getattr(service, "partial_warning", None):
        tool_event["warning"] = service.partial_warning
        service.partial_warning = None
    yield tool_event
    return result, parsed_result, is_error


_SENTINEL = object()


def _run_safe_events(make_events: Callable[[Callable[[dict], None]], Iterator[dict]]):
    """Run `make_events(emit_live)` - _run_agent_events or _run_direct_events
    with their arguments already bound - in a background thread, relaying every event -
    including live "api_call" progress fired from inside a single tool call -
    to the caller the instant it happens, via a queue.

    This is what makes the API-call counter update live: a plain generator
    can only yield from its own stack frame, so without a separate thread
    pushing into a queue, an "api_call" event fired deep inside a blocking
    tool call (e.g. the 30th of 100 per-follower lookups) would never reach
    the caller until the whole tool call returns - the queue decouples "when
    the work happens" from "when we yield", so it can be relayed immediately
    even while the worker thread is still blocked deeper in the call stack.

    Also turns Ollama connectivity errors into an "error" event instead of an
    exception - needed because once a streaming response has started, raising
    HTTPException can no longer change the HTTP status code.
    """
    q: "queue.Queue[dict]" = queue.Queue()

    def worker():
        try:
            for event in make_events(q.put):
                q.put(event)
        except QueryCancelledError:
            pass  # the user stopped the search - nothing left to report
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            q.put({
                "type": "error",
                "detail": (
                    f"Cannot reach LM Studio at {resolve_lmstudio_host()}: {e}. Make sure LM Studio "
                    f"is running and the local server is started (default port 1234)."
                ),
            })
        except httpx.HTTPStatusError as e:
            q.put({
                "type": "error",
                "detail": f"LM Studio returned HTTP {e.response.status_code}: {e.response.text[:200]}",
            })
        except httpx.HTTPError as e:
            q.put({"type": "error", "detail": f"LM Studio communication error: {e}"})
        except ConnectionError as e:
            llm_info = resolve_llm_info()
            if llm_info.get("provider") == "lmstudio":
                err_detail = (
                    f"Cannot reach LM Studio at {llm_info.get('base_url', 'http://127.0.0.1:1234/v1')}: {e}. "
                    "Make sure LM Studio is running with local server started on port 1234."
                )
            else:
                err_detail = (
                    f"Cannot reach Ollama: {e}. Make sure it is running "
                    f"(`ollama serve`) and that the model has been pulled "
                    f"(`ollama pull {OLLAMA_MODEL}`)."
                )
            q.put({"type": "error", "detail": err_detail})
        except Exception as e:
            if ollama and isinstance(e, getattr(ollama, "ResponseError", ())):
                q.put({"type": "error", "detail": f"Ollama error: {e}"})
            else:
                q.put({"type": "error", "detail": f"LLM error: {e}"})
        finally:
            q.put(_SENTINEL)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = q.get()
        if item is _SENTINEL:
            return
        yield item


def _sse(event: dict) -> str:
    # Belt-and-braces: _run_agent_events already sanitizes tool results, but
    # this also covers the "start"/"answer" events and any string built from
    # raw backend data (target username, api_call detail...) so a single bad
    # character can never silently kill the stream (see _sanitize_unicode).
    event = _sanitize_unicode(event)
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


REPOSITORY_URL = "https://github.com/Datalux/Osintgram"
# Third-party libraries the web UI runs on, credited in the page footer:
# (distribution name, what it's used for, project URL). Version and license
# are read from the installed package's own metadata, so the credits always
# match what's actually deployed.
THIRD_PARTY = [
    ("fastapi", "server web e API", "https://fastapi.tiangolo.com"),
    ("uvicorn", "server ASGI", "https://www.uvicorn.org"),
    ("pydantic", "data validation", "https://docs.pydantic.dev"),
    ("hikerapi", "backend Instagram (HikerAPI)", "https://hikerapi.com"),
    ("instagrapi", "backend Instagram alternativo", "https://github.com/subzeroid/instagrapi"),
    ("ollama", "local model client", "https://github.com/ollama/ollama-python"),
    ("httpx", "HTTP & LM Studio client", "https://www.python-httpx.org"),
    ("geopy", "geocodifica inversa (Nominatim)", "https://github.com/geopy/geopy"),
]


def _library_credit(dist: str, role: str, url: str) -> dict:
    try:
        meta = metadata.metadata(dist)
    except metadata.PackageNotFoundError:
        return {"name": dist, "role": role, "url": url, "version": None, "license": None}
    license_ = meta.get("License-Expression") or meta.get("License") or ""
    if not license_ or len(license_) > 40:  # some packages put the full license text here
        classifiers = [c for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
        license_ = classifiers[0].split(" :: ")[-1] if classifiers else None
    return {"name": dist, "role": role, "url": url, "version": meta["Version"], "license": license_}


@app.get("/api/about")
def about():
    """The header's logo and version line (the CLI's own src/artwork.py) and
    the footer's project/credits info."""
    backend = resolve_llm_backend()
    active_model = resolve_lmstudio_model() if backend == "lmstudio" else OLLAMA_MODEL
    return {
        "logo": artwork.ascii_art,
        "version": artwork.version,
        "author": artwork.author,
        "repository": REPOSITORY_URL,
        "license": {"name": "GPL-3.0", "url": f"{REPOSITORY_URL}/blob/master/LICENSE"},
        "libraries": [_library_credit(*lib) for lib in THIRD_PARTY],
        # Shown in the footer's attribution: the model's own license terms
        # apply on top of Ollama's (e.g. "Built with Llama" for Llama models).
        "ollama_model": f"{resolve_llm_info()['provider'].upper()}: {resolve_llm_info()['model']}",
        "llm_backend": resolve_llm_info()["provider"],
    }


@app.get("/api/balance")
def balance():
    """Remaining HikerAPI quota for the header (free: HikerAPI doesn't bill
    this lookup). {"available": false} when another backend is in use."""
    try:
        data = hiker_balance()
    except OsintServiceError as e:
        raise HTTPException(502, str(e)) from e
    return {"available": False} if data is None else {"available": True, **data}


@app.delete("/api/cache")
def clear_cache():
    """Drop every cached backend response (the CLI's `cache` command)."""
    if isinstance(_RAW_CALL_CACHE, dict):  # in-memory mode (HIKER_CACHE_PATH="")
        cleared = len(_RAW_CALL_CACHE)
        _RAW_CALL_CACHE.clear()
    else:
        cleared = _RAW_CALL_CACHE.clear()
    return {"cleared": cleared}


@app.get("/api/tools")
def list_tools():
    """Commands and their parameters, for the web UI's manual ("Base") mode."""
    return TOOL_SPECS


@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not (req.message or "").strip():
        raise HTTPException(400, "Type a request.")
    # The target is optional: with none set the agent still runs, restricted
    # to the searches that belong to no account (hashtag, place) - see
    # _run_agent_events.
    service = _build_service_or_http_error((req.target or "").strip() or None)
    history.queries.record(req.message)
    return _respond(
        req,
        service,
        lambda emit_live: _run_agent_events(
            service, req.message, max_items=req.max_items, cache_ttl_seconds=req.cache_ttl_seconds, emit_live=emit_live
        ),
    )


@app.post("/api/run", response_model=QueryResponse)
def run(req: RunRequest):
    if not req.calls:
        raise HTTPException(400, "Select at least one command.")
    unknown = sorted({call.name for call in req.calls} - TOOL_NAMES)
    if unknown:
        raise HTTPException(400, f"Unknown command: {', '.join(unknown)}")
    needs_target = [c.name for c in req.calls if c.name not in TARGET_FREE_TOOLS]
    if needs_target and not (req.target or "").strip():
        raise HTTPException(400, f"A target username is required for: {', '.join(sorted(set(needs_target)))}")
    service = _build_service_or_http_error(req.target if needs_target else None)
    return _respond(
        req,
        service,
        lambda emit_live: _run_direct_events(
            service, req.calls, max_items=req.max_items, cache_ttl_seconds=req.cache_ttl_seconds, emit_live=emit_live
        ),
    )


_HISTORIES = {"targets": history.targets, "queries": history.queries}


def _history_or_404(kind: str) -> history.History:
    if kind not in _HISTORIES:
        raise HTTPException(404, f"Storico sconosciuto: {kind}")
    return _HISTORIES[kind]


@app.get("/api/history/{kind}")
def get_history(kind: str):
    """Recent target usernames ("targets") or AI requests ("queries"), most
    recent first - the dropdowns under the search fields."""
    return _history_or_404(kind).list_entries()


@app.delete("/api/history/{kind}")
def delete_history_entry(kind: str, value: str):
    # `value` as a query parameter, not a path segment: a request's free
    # text can contain "/" or "?", which a path parameter can't carry.
    return _history_or_404(kind).remove(value)


def _build_service_or_http_error(target: str) -> OsintgramService:
    try:
        service = build_service(target)
    except TargetNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except OsintServiceError as e:
        raise HTTPException(502, str(e)) from e
    # Recorded only once the target actually resolved, under the username
    # Instagram returned (canonical spelling), not whatever was typed.
    if target:
        history.targets.record(service.user.get("username") or target)
    return service


class TokenRequest(BaseModel):
    token: str
    remember: bool = True


def _token_state() -> dict:
    """What the UI needs to show about the key - never the key itself."""
    source = hiker_token_source()
    return {
        "configured": source is not None,
        # "env" means HIKERAPI_TOKEN wins over anything typed here; the UI
        # says so instead of letting a pasted key look like it took effect.
        "source": source,
        "locked": source == "env",
        "preview": mask_token(resolve_hiker_token()),
    }


@app.get("/api/token")
def get_token_state():
    return _token_state()


@app.post("/api/token")
def set_token(req: TokenRequest, request: Request):
    """Accept a HikerAPI key typed into the UI, after checking it works.

    The key is verified against HikerAPI's free /sys/balance before being
    accepted, so a typo is reported here rather than as a failed search later.
    It is never returned by any endpoint afterwards - only a masked preview.
    """
    _require_local_origin(request)
    token = (req.token or "").strip()
    if not token:
        raise HTTPException(400, "Paste a HikerAPI key.")
    try:
        balance = check_hiker_token(token)
    except OsintServiceError as e:
        raise HTTPException(400, f"Key rejected by HikerAPI: {e}") from e

    set_runtime_hiker_token(token)
    saved = False
    if req.remember:
        try:
            save_hiker_token(token)
            saved = True
        except OSError as e:
            # The key still works for this session - say so rather than
            # failing a request that did succeed.
            return {**_token_state(), "balance": balance, "saved": False,
                    "warning": f"Key active but not saved to file: {e}"}
    return {**_token_state(), "balance": balance, "saved": saved}


@app.delete("/api/token")
def clear_token(request: Request):
    """Forget the key entered in this session. One saved in credentials.ini
    (or HIKERAPI_TOKEN) stays - removing those is a deliberate, out-of-band
    act, not something a web page should do behind the user's back."""
    _require_local_origin(request)
    set_runtime_hiker_token(None)
    return _token_state()


class AISettingsRequest(BaseModel):
    provider: str
    base_url: str
    model: Optional[str] = ""
    api_key: Optional[str] = ""
    remember: bool = True


@app.get("/api/ai/settings")
def get_ai_settings():
    """Return current AI provider settings and connectivity state."""
    info = resolve_llm_info()
    models = []
    connected = False
    try:
        models = fetch_available_models(info["provider"], info["base_url"], info.get("api_key", ""))
        connected = True
    except Exception:
        pass
    raw_key = info.get("api_key", "")
    return {
        "provider": info["provider"],
        "base_url": info["base_url"],
        "model": info["model"],
        "has_api_key": bool(raw_key),
        "api_key_preview": mask_token(raw_key) if raw_key else "",
        "models": models,
        "connected": connected,
    }


@app.post("/api/ai/settings")
def update_ai_settings(req: AISettingsRequest, request: Request):
    """Update and verify AI provider settings, optionally saving to config/credentials.ini."""
    _require_local_origin(request)
    provider = (req.provider or "lmstudio").strip().lower()
    base_url = (req.base_url or "").strip()
    if not base_url:
        base_url = "http://127.0.0.1:1234/v1" if provider in ("lmstudio", "openai") else "http://127.0.0.1:11434"

    api_key = (req.api_key or "").strip()
    # Test connection and fetch available models
    models = []
    try:
        models = fetch_available_models(provider, base_url, api_key)
    except Exception as e:
        raise HTTPException(400, f"Cannot connect to {provider} at {base_url}: {e}")

    model = (req.model or "").strip()
    if not model and models:
        model = models[0]

    set_runtime_ai_config({
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
    })

    saved = False
    if req.remember:
        saved = save_ai_config(provider, base_url, model, api_key)

    return {
        "ok": True,
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "models": models,
        "saved": saved,
        "connected": True,
    }


@app.get("/api/ai/models")
def get_ai_models(provider: str = "lmstudio", base_url: str = "", api_key: str = ""):
    """Query the active provider for its list of models."""
    provider = provider.strip().lower()
    if not base_url:
        base_url = "http://127.0.0.1:1234/v1" if provider in ("lmstudio", "openai") else "http://127.0.0.1:11434"
    try:
        models = fetch_available_models(provider, base_url, api_key)
        return {"ok": True, "models": models}
    except Exception as e:
        raise HTTPException(400, f"Cannot fetch models from {provider} at {base_url}: {e}")


class WebSearchSettingsRequest(BaseModel):
    enabled: bool = False
    provider: str = "duckduckgo"
    searxng_url: Optional[str] = "http://127.0.0.1:8080"
    parallel_api_key: Optional[str] = ""
    remember: bool = True


@app.get("/api/ai/websearch")
def get_websearch_settings():
    from src.web.web_search import resolve_web_search_config
    cfg = resolve_web_search_config()
    return {
        "enabled": cfg.enabled,
        "provider": cfg.provider,
        "searxng_url": cfg.searxng_url,
        "has_parallel_key": bool(cfg.parallel_api_key),
    }


@app.post("/api/ai/websearch")
def update_websearch_settings(req: WebSearchSettingsRequest, request: Request):
    _require_local_origin(request)
    from src.web.web_search import WebSearchConfig, set_runtime_web_search_config, save_web_search_config
    cfg = WebSearchConfig(
        enabled=req.enabled,
        provider=(req.provider or "duckduckgo").strip().lower(),
        searxng_url=(req.searxng_url or "http://127.0.0.1:8080").strip(),
        parallel_api_key=(req.parallel_api_key or "").strip(),
    )
    set_runtime_web_search_config(cfg)
    saved = False
    if req.remember:
        saved = save_web_search_config(cfg)
    return {"ok": True, "enabled": cfg.enabled, "provider": cfg.provider, "saved": saved}


def mask_proxy(proxy_url: str) -> str:
    if not proxy_url:
        return ""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(proxy_url)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        if parsed.username:
            return f"{scheme}://{parsed.username}:***@{host}{port}"
        return f"{scheme}://{host}{port}"
    except Exception:
        return proxy_url[:8] + "***"


class ProxySettingsRequest(BaseModel):
    proxy: str = ""
    remember: bool = True


@app.get("/api/proxy/settings")
def get_proxy_settings():
    from src.instagrapi_backend import resolve_instagrapi_proxy
    proxy = resolve_instagrapi_proxy()
    return {
        "configured": bool(proxy),
        "preview": mask_proxy(proxy) if proxy else "",
    }


@app.post("/api/proxy/settings")
def update_proxy_settings(req: ProxySettingsRequest, request: Request):
    _require_local_origin(request)
    from src.instagrapi_backend import resolve_instagrapi_proxy
    proxy = (req.proxy or "").strip()

    # Test proxy if provided (optional check via httpbin.org)
    test_warning = None
    origin_ip = None
    if proxy and req.test_connectivity:
        import httpx
        try:
            with httpx.Client(proxy=proxy, timeout=5.0) as client:
                r = client.get("https://httpbin.org/ip")
                if r.status_code == 200:
                    origin_ip = r.json().get("origin", "")
        except Exception as e:
            # httpbin.org can be throttled or unreachable; do not fail a valid proxy setup
            test_warning = f"Could not verify egress IP via httpbin.org ({e}). Proxy settings were saved." 

    # Persist or clear in credentials.ini
    saved = False
    if req.remember:
        cp = configparser.ConfigParser(interpolation=None)
        cred_path = Path("config/credentials.ini")
        if cred_path.exists():
            try:
                cp.read(cred_path, encoding="utf-8")
            except Exception:
                pass
        if not cp.has_section("Credentials"):
            cp.add_section("Credentials")
        if proxy:
            cp.set("Credentials", "proxy", proxy)
        elif cp.has_option("Credentials", "proxy"):
            cp.remove_option("Credentials", "proxy")
        cred_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cred_path, "w", encoding="utf-8") as f:
            cp.write(f)
        saved = True

    if proxy:
        os.environ["INSTAGRAPI_PROXY"] = proxy
    else:
        os.environ.pop("INSTAGRAPI_PROXY", None)

    return {
        "ok": True,
        "configured": bool(proxy),
        "preview": mask_proxy(proxy) if proxy else "",
        "saved": saved,
        "origin_ip": origin_ip,
        "warning": test_warning,
    }


class GraphExportRequest(BaseModel):
    target: str = "target"
    results: list = []
    format: str = "gexf"


@app.post("/api/export/graph")
def export_network_graph(req: GraphExportRequest, request: Request):
    """Export social network graph from scan results to GEXF (for Gephi) or JSON."""
    _require_local_origin(request)
    content_len = request.headers.get("content-length")
    if content_len and int(content_len) > 10 * 1024 * 1024:
        raise HTTPException(413, "Payload too large (maximum 10MB)")
    if len(req.results) > 10000:
        raise HTTPException(400, "Too many results for graph export (maximum 10,000 items)")

    from src.web.graph_export import build_social_graph, export_gexf
    graph = build_social_graph(req.results, target=req.target)
    safe_target = re.sub(r"[^\w.-]+", "_", req.target or "target")

    if req.format.lower() == "json":
        body = json.dumps(graph, ensure_ascii=False, indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{safe_target}_network.json"'},
        )
    else:
        gexf_content = export_gexf(graph)
        return Response(
            content=gexf_content,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{safe_target}_network.gexf"'},
        )


class DownloadRequest(BaseModel):
    urls: list
    name: str = "media" 


@app.post("/api/download")
def download_media(req: DownloadRequest):
    """Pack the given Instagram media into one zip for the browser to save."""
    try:
        content, report = download.build_zip(req.urls)
    except download.DownloadError as e:
        raise HTTPException(400, str(e)) from e
    filename = f"osintgram_{re.sub(r'[^A-Za-z0-9._-]+', '_', req.name)[:60] or 'media'}.zip"
    return Response(
        content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Read by the page to report what actually made it into the zip.
            "X-Download-Report": json.dumps(report),
            "Access-Control-Expose-Headers": "X-Download-Report",
        },
    )


@app.post("/api/dossier")
def save_dossier(run: dict, request: Request):
    """Store a finished search so it can be reopened for free later - and
    compared with a later run of the same target."""
    _require_local_origin(request)
    if not run.get("target"):
        raise HTTPException(400, "The dossier is missing its target.")
    return dossier.save(run)


@app.get("/api/dossier")
def list_dossiers(request: Request, target: Optional[str] = None):
    _require_local_origin(request)
    return dossier.list_for(target)


@app.get("/api/dossier/{target}/{dossier_id}")
def get_dossier(target: str, dossier_id: str, request: Request):
    _require_local_origin(request)
    run = dossier.load(target, dossier_id)
    if run is None:
        raise HTTPException(404, "Dossier not found.")
    return run


@app.delete("/api/dossier/{target}/{dossier_id}")
def delete_dossier(target: str, dossier_id: str, request: Request):
    _require_local_origin(request)
    return {"deleted": dossier.delete(target, dossier_id)}


@app.get("/api/dossier/{target}/{before_id}/diff/{after_id}")
def diff_dossiers(target: str, before_id: str, after_id: str, request: Request):
    """What changed between two saved runs of the same target."""
    _require_local_origin(request)
    before, after = dossier.load(target, before_id), dossier.load(target, after_id)
    if before is None or after is None:
        raise HTTPException(404, "Dossier not found.")
    if before.get("saved_at", 0) > after.get("saved_at", 0):
        before, after = after, before  # always compare oldest -> newest
    return dossier.compare(before, after)


@app.post("/api/estimate")
def estimate_cost(req: RunRequest):
    """How many backend requests the selected commands are likely to cost.

    Needs the target's own counters, so it resolves the profile: one request,
    which the run itself would spend anyway and which the request cache then
    serves (so estimating before running is effectively free)."""
    if not req.calls:
        raise HTTPException(400, "Select at least one command.")
    service = _build_service_or_http_error(req.target)
    service.api.cache_store = _RAW_CALL_CACHE
    service.api.cache_ttl_seconds = _resolve_ttl(req.cache_ttl_seconds)
    calls = [{"name": c.name, "args": resolve_call_args(_TOOL_FUNCS.get(c.name), c.args, req.max_items)}
             for c in req.calls]
    result = cost.estimate(calls, service.user, req.max_items)
    result["profile"] = {
        "media_count": service.user.get("media_count"),
        "follower_count": service.user.get("follower_count"),
        "following_count": service.user.get("following_count"),
    }
    return result


@app.post("/api/cancel")
def cancel(req: CancelRequest):
    """Stop a running search. The browser aborting its own request would leave
    the worker running - and spending HikerAPI requests - to the end."""
    with _CANCELLATIONS_LOCK:
        event = _CANCELLATIONS.get(req.run_id)
    if event is not None:
        event.set()
    return {"cancelled": event is not None}


def _respond(req: _BaseRequest, service: OsintgramService, make_events):
    """Either stream every event as SSE (verbose) or run to completion and
    return one QueryResponse - identical for both modes; in manual mode there
    is simply no "answer" event, so `answer` stays empty."""
    if req.verbose:
        def stream():
            with _cancellation(req.run_id) as cancelled:
                service.api.cancelled = cancelled
                # Chrome (and other browsers) buffer the first chunk(s) of a
                # fetch() streaming response internally until a minimum byte
                # threshold is reached, only handing anything to JS once that's
                # met or the connection closes - our real events are a few
                # hundred bytes each, well under it, so without this the whole
                # SSE stream would arrive to the page in one burst at the end
                # even though the server sends it correctly spaced out (verified
                # with curl). A leading SSE comment line (ignored by any
                # compliant parser, and by our own client code, which only acts
                # on lines starting with "data: ") pushes past that threshold
                # immediately so real events start flowing to the page live.
                yield ":" + " " * 2048 + "\n\n"
                try:
                    for event in _run_safe_events(make_events):
                        yield _sse(event)
                finally:
                    # Reached both on a normal end and when the client goes
                    # away (tab closed, network drop) and Starlette closes
                    # this generator: stop the worker from spending more.
                    cancelled.set()

        return StreamingResponse(stream(), media_type="text/event-stream")

    answer = ""
    tool_calls: list = []
    error_detail = None
    with _cancellation(req.run_id) as cancelled:
        service.api.cancelled = cancelled
        for event in _run_safe_events(make_events):
            if event["type"] == "tool_call":
                tool_calls.append({"name": event["name"], "input": event["input"]})
            elif event["type"] == "tool_result":
                for tc in reversed(tool_calls):
                    if tc["name"] == event["name"] and "result" not in tc:
                        tc["result"] = event["result"]
                        tc["is_error"] = event["is_error"]
                        tc["elapsed_ms"] = event["elapsed_ms"]
                        tc["api_calls_delta"] = event["api_calls_delta"]
                        break
            elif event["type"] == "answer":
                answer = event["text"]
            elif event["type"] == "error":
                error_detail = event["detail"]

    if error_detail is not None:
        raise HTTPException(502, error_detail)

    return QueryResponse(
        target=req.target,
        target_id=service.target_id,
        backend=service.backend_name,
        api_calls_total=service.api_call_count,
        answer=answer,
        tool_calls=tool_calls,
    )


@app.middleware("http")
async def _response_headers(request, call_next):
    response = await call_next(request)
    # This app's whole frontend is one HTML file that has changed release to
    # release during development - browsers otherwise cache it (via
    # heuristics or a stale tab), silently running old JavaScript after an
    # update. Blanket no-store is irrelevant for perf at this scale (a
    # single local user) and removes that whole class of "it's still doing
    # the old thing" confusion. It also keeps OSINT results out of disk caches.
    response.headers["Cache-Control"] = "no-store"
    # Baseline hardening: no MIME sniffing, no framing by other sites
    # (clickjacking), no referrer leaking the local URL to the CDN/GitHub
    # links the page opens, no search-engine indexing, and no browser
    # features the page never uses.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


class SnapshotRequest(BaseModel):
    include_network: bool = False
    limit_network: int = 200


class WebhookTestRequest(BaseModel):
    webhook_url: str
    target: str = "test_target"
    chat_id: Optional[str] = None


class WebhookNotifyRequest(BaseModel):
    webhook_url: str
    target: str
    diff_data: dict
    chat_id: Optional[str] = None


@app.post("/api/target/{target}/snapshot")
def create_target_snapshot(target: str, req: SnapshotRequest, request: Request):
    _require_local_origin(request)
    service = build_service(target)
    limit_net = min(500, max(1, req.limit_network or 200))
    try:
        snap = service.take_snapshot(
            include_network=req.include_network,
            limit_network=limit_net,
        )
        return {"ok": True, "snapshot": snap}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/target/{target}/snapshots")
def get_target_snapshots(target: str, limit: int = 50):
    from src.snapshot_tracker import list_snapshots
    return {"ok": True, "snapshots": list_snapshots(target, limit=limit)}


@app.delete("/api/target/{target}/snapshots")
@app.delete("/api/snapshot/{target}")
def delete_target_snapshots(target: str, request: Request):
    _require_local_origin(request)
    from src.snapshot_tracker import delete_snapshots
    count = delete_snapshots(target)
    return {"ok": True, "target": target, "deleted_count": count}


@app.get("/api/target/{target}/diff")
def get_target_diff(target: str, old_id: Optional[int] = None, new_id: Optional[int] = None):
    from src.snapshot_tracker import compare_snapshots, diff_latest_two, get_snapshot
    if old_id is not None and new_id is not None:
        old_snap = get_snapshot(old_id)
        new_snap = get_snapshot(new_id)
        if not old_snap or not new_snap:
            raise HTTPException(404, f"Snapshot not found (old_id={old_id}, new_id={new_id})")
        diff = compare_snapshots(old_snap, new_snap)
    else:
        diff = diff_latest_two(target)
        if diff is None:
            raise HTTPException(404, f"At least 2 snapshots are required to calculate diff for @{target}")
    return {"ok": True, "diff": diff}


@app.post("/api/webhook/test")
def test_webhook_dispatch(req: WebhookTestRequest, request: Request):
    _require_local_origin(request)
    from src.webhook_dispatcher import dispatch_webhook
    fake_diff = {
        "target": req.target,
        "has_changes": True,
        "summary": ["Test notification from Osintgram Watcher.", "Followers: +5 new accounts."],
        "metric_deltas": {
            "followers": {"old": 100, "new": 105, "diff": 5},
            "following": {"old": 50, "new": 50, "diff": 0},
        },
        "network_changes": {
            "new_followers": ["sample_user_1", "sample_user_2"],
            "lost_followers": [],
        },
    }
    res = dispatch_webhook(req.webhook_url, "test_notification", fake_diff, target=req.target, chat_id=req.chat_id)
    return res


@app.post("/api/webhook/notify-diff")
def send_webhook_diff_notification(req: WebhookNotifyRequest, request: Request):
    _require_local_origin(request)
    from src.webhook_dispatcher import dispatch_webhook
    res = dispatch_webhook(req.webhook_url, "profile_diff", req.diff_data, target=req.target, chat_id=req.chat_id)
    return res


# Registered last so it doesn't shadow /api/query.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
