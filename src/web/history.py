"""Persistent search histories for the web UI's dropdowns: searched target
usernames, and natural-language requests made in AI mode.

Stored server-side as JSON files (config/, kept out of git by .gitignore's
`**/*.json`) rather than in the browser's localStorage, so they survive
restarts of the tool regardless of browser, profile, or whether the page was
opened as localhost or 127.0.0.1 (different origins, separate storage).

Entries are only recorded once the target actually resolved to an Instagram
account (see src/web/app.py) - a typo never pollutes either history.
"""
import json
import os
import threading
import time
from pathlib import Path
from typing import Callable

MAX_ENTRIES = 50


class History:
    """Most-recent-first list of unique values, persisted to one JSON file.

    `key` decides when two values are the same entry (re-recording one moves
    it to the top instead of adding a duplicate); `clean` is the form that
    gets stored and shown.
    """

    def __init__(self, path: Path, key: Callable[[str], str], clean: Callable[[str], str]):
        self.path = path
        self._key = key
        self._clean = clean
        # FastAPI runs sync endpoints in a thread pool - two searches
        # finishing at once must not interleave their read-modify-write.
        self._lock = threading.Lock()

    def _load(self) -> list:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []  # missing or corrupt file - start over rather than fail the UI
        if not isinstance(data, list):
            return []
        entries = []
        for e in data:
            # "username" is the field name the first version of the target
            # history was saved with.
            value = e.get("value", e.get("username")) if isinstance(e, dict) else None
            if isinstance(value, str):
                entries.append({"value": value, "last_searched_at": e.get("last_searched_at") or 0})
        return entries

    def _save(self, entries: list) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename so a crash mid-write can't leave a truncated file.
        # Still ends in .json so a leftover temp file is git-ignored too.
        tmp = self.path.with_name(self.path.stem + ".tmp.json")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def list_entries(self) -> list:
        """Entries as {"value", "last_searched_at" (unix seconds)}, most recent first."""
        with self._lock:
            return self._load()

    def record(self, value: str) -> None:
        """Move `value` to the top of the history (adding it if new).

        Never raises: the history is a convenience, and a disk problem saving
        it must not fail the search that triggered it.
        """
        key = self._key(value)
        if not key:
            return
        with self._lock:
            entries = [e for e in self._load() if self._key(e["value"]) != key]
            entries.insert(0, {"value": self._clean(value), "last_searched_at": int(time.time())})
            try:
                self._save(entries[:MAX_ENTRIES])
            except OSError:
                pass

    def remove(self, value: str) -> list:
        """Delete `value` from the history; returns the updated entries."""
        key = self._key(value)
        with self._lock:
            entries = [e for e in self._load() if self._key(e["value"]) != key]
            self._save(entries)
            return entries


# Instagram usernames are case-insensitive; "@x" and "x" are the same.
targets = History(
    Path("config/search_history.json"),
    key=lambda v: v.strip().lstrip("@").lower(),
    clean=lambda v: v.strip().lstrip("@"),
)

# Requests differing only in case or spacing are the same request.
queries = History(
    Path("config/query_history.json"),
    key=lambda v: " ".join(v.split()).casefold(),
    clean=lambda v: v.strip(),
)
