"""Saved searches ("dossier") and what changed between two of them.

A search's results only ever lived in the page until now: reloading lost
them, and re-running one cost the HikerAPI requests all over again. A dossier
is one finished run stored as a JSON file, so it can be reopened for free -
and, more usefully for OSINT, compared with a later run of the same target to
see what changed: new/lost followers, an edited bio, new posts.

Files live under dossier/<target>/<timestamp>.json - third parties' personal
data, so .gitignore and .dockerignore keep the directory out of commits and
images.
"""
import json
import re
import secrets
import time
from pathlib import Path
from typing import Optional

DOSSIER_DIR = Path("dossier")

# Result keys that are presentation-only or inherently volatile (signed CDN
# URLs change on every fetch), so comparing them would report noise.
_IGNORED_FIELDS = {"previews", "timestamps", "thumbnail_url", "media_url", "url", "profile_pic_url"}

# How to identify "the same item" across two runs, by result shape.
_IDENTITY_FIELDS = ("pk", "id", "username", "hashtag", "address", "description")


def _safe(name: str) -> str:
    """Filesystem-safe form of a username / id (also blocks path traversal)."""
    return re.sub(r"[^\w.@-]+", "_", str(name))[:80] or "_"


def _path(target: str, dossier_id: str) -> Path:
    return DOSSIER_DIR / _safe(target) / f"{_safe(dossier_id)}.json"


def save(run: dict) -> dict:
    """Store one finished run; returns its summary (id, target, saved_at...)."""
    target = run.get("target") or "unknown"
    saved_at = int(time.time())
    # Timestamp *and* a random suffix: two saves within the same second must
    # not overwrite each other (the id is also the file name).
    dossier_id = f"{saved_at}-{secrets.token_hex(3)}"
    path = _path(target, dossier_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = {**run, "id": dossier_id, "target": target, "saved_at": saved_at}
    path.write_text(json.dumps(stored, ensure_ascii=False, indent=1), encoding="utf-8")
    return _summary(stored)


def _summary(run: dict) -> dict:
    results = run.get("results") or []
    return {
        "id": run.get("id"),
        "target": run.get("target"),
        "saved_at": run.get("saved_at"),
        "mode": run.get("mode"),
        "request": run.get("request"),
        "commands": [r.get("name") for r in results],
        "api_calls": run.get("api_calls_total"),
    }


def list_for(target: Optional[str] = None) -> list:
    """Saved runs, newest first - for one target or across all of them."""
    roots = [DOSSIER_DIR / _safe(target)] if target else (
        sorted(DOSSIER_DIR.iterdir()) if DOSSIER_DIR.exists() else []
    )
    summaries = []
    for root in roots:
        if not root.is_dir():
            continue
        for file in root.glob("*.json"):
            try:
                summaries.append(_summary(json.loads(file.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                continue  # a corrupt file must not break the list
    # Newest first; the id breaks ties between same-second saves.
    return sorted(summaries, key=lambda s: (s.get("saved_at") or 0, s.get("id") or ""), reverse=True)


def load(target: str, dossier_id: str) -> Optional[dict]:
    try:
        return json.loads(_path(target, dossier_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def delete(target: str, dossier_id: str) -> bool:
    try:
        _path(target, dossier_id).unlink()
        return True
    except OSError:
        return False


# ---- comparison ----

def _identity(item):
    """A stable key for an item across runs, or None if it has no usable one."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for field in _IDENTITY_FIELDS:
            if item.get(field) is not None:
                return f"{field}={item[field]}"
    return None


def _label(item):
    """Short human-readable form of an item, for the diff output."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for field in ("username", "hashtag", "address", "title", "description"):
            if item.get(field):
                return str(item[field])
        return _identity(item) or json.dumps(item, ensure_ascii=False)[:80]
    return str(item)


def _diff_lists(old: list, new: list) -> dict:
    old_keys = {_identity(i): i for i in old}
    new_keys = {_identity(i): i for i in new}
    if None in old_keys or None in new_keys:
        # No stable identity (e.g. plain numbers): fall back to counting.
        return {"added": [], "removed": [], "count_before": len(old), "count_after": len(new)}
    return {
        "added": [_label(i) for k, i in new_keys.items() if k not in old_keys],
        "removed": [_label(i) for k, i in old_keys.items() if k not in new_keys],
        "count_before": len(old),
        "count_after": len(new),
    }


def _diff_dicts(old: dict, new: dict) -> list:
    changed = []
    for key in sorted(set(old) | set(new)):
        if key in _IGNORED_FIELDS:
            continue
        before, after = old.get(key), new.get(key)
        if isinstance(before, (dict, list)) or isinstance(after, (dict, list)):
            continue  # nested structures are compared as lists elsewhere
        if before != after:
            changed.append({"field": key, "from": before, "to": after})
    return changed


def _results_by_name(run: dict) -> dict:
    return {r.get("name"): r.get("result") for r in run.get("results") or [] if r.get("name")}


def compare(before: dict, after: dict) -> dict:
    """What changed between two saved runs of the same target."""
    old_results, new_results = _results_by_name(before), _results_by_name(after)
    commands = []
    for name in sorted(set(old_results) & set(new_results)):
        old, new = old_results[name], new_results[name]
        entry = {"name": name}
        if isinstance(old, list) and isinstance(new, list):
            entry.update(_diff_lists(old, new))
        elif isinstance(old, dict) and isinstance(new, dict):
            entry["changed"] = _diff_dicts(old, new)
            # A dict result may still carry its own list (e.g. "descriptions").
            for key in set(old) & set(new):
                if key in _IGNORED_FIELDS:
                    continue
                if isinstance(old[key], list) and isinstance(new[key], list):
                    nested = _diff_lists(old[key], new[key])
                    if nested["added"] or nested["removed"]:
                        entry.setdefault("added", []).extend(nested["added"])
                        entry.setdefault("removed", []).extend(nested["removed"])
        else:
            entry["changed"] = [] if old == new else [{"field": "result", "from": _label(old), "to": _label(new)}]
        entry["unchanged"] = not (entry.get("added") or entry.get("removed") or entry.get("changed"))
        commands.append(entry)
    return {
        "target": after.get("target"),
        "before": {"id": before.get("id"), "saved_at": before.get("saved_at")},
        "after": {"id": after.get("id"), "saved_at": after.get("saved_at")},
        "only_in_before": sorted(set(old_results) - set(new_results)),
        "only_in_after": sorted(set(new_results) - set(old_results)),
        "commands": commands,
    }
