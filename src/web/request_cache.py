"""Disk-backed store for OsintgramService's per-request cache.

The web UI caches every raw Hiker/instagrapi response (see
_CountingApiProxy in src/osint_service.py); kept only in memory, that cache
was lost on every restart of the tool, so the same requests - real cost on
HikerAPI's paid quota - got paid for again. This keeps it in a SQLite file
instead, so cached responses survive restarts for as long as their TTL.

The file holds third parties' Instagram data: it lives under cache/, which
.gitignore and .dockerignore keep out of commits and images.

The cache is strictly a cost optimization, never a source of truth: any disk
problem (a read-only file, a deleted cache dir, a locked database) must never
fail the search it was serving. Every DB operation is best-effort, and the
first write failure transparently drops the whole cache to an in-memory dict
for the rest of the process, so queries keep working (just not persisted).
"""
import json
import sqlite3
import sys
import threading
import time
from pathlib import Path

# Expired rows are purged on startup and then once every this many writes,
# so a long-running server doesn't grow the file forever.
_PURGE_EVERY_WRITES = 500


class PersistentRequestCache:
    """Dict-like store (``get`` / item assignment, the only two operations
    _CountingApiProxy uses) of ``(method, args, kwargs) -> (expires_at,
    response)``, with ``expires_at`` in wall-clock unix seconds so it stays
    meaningful across restarts. A response that can't be stored as JSON is
    simply not cached."""

    def __init__(self, path: Path):
        self._lock = threading.Lock()
        self._writes = 0
        # In-memory fallback ({key_str: (expires_at, value)}); populated only
        # if the database becomes unusable, at which point _db is dropped.
        self._memory = None
        self._db = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # One connection shared by FastAPI's worker threads, serialized by the lock.
            self._db = sqlite3.connect(path, check_same_thread=False)
            with self._lock, self._db:
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS responses "
                    "(key TEXT PRIMARY KEY, expires_at REAL NOT NULL, value TEXT NOT NULL)"
                )
            self.purge_expired()
        except (sqlite3.Error, OSError) as e:
            self._degrade(e)

    def _degrade(self, error) -> None:
        """Give up on the disk cache and continue in memory - once."""
        if self._memory is None:
            self._memory = {}
            self._db = None
            print(f"[request_cache] disk cache disabled, using memory instead: {error}", file=sys.stderr)

    @staticmethod
    def _key(key) -> str:
        return json.dumps(key, default=str)

    def get(self, key):
        key = self._key(key)
        if self._memory is not None:
            row = self._memory.get(key)
        else:
            try:
                with self._lock:
                    row = self._db.execute(
                        "SELECT expires_at, value FROM responses WHERE key = ?", (key,)
                    ).fetchone()
                if row is not None:
                    row = (row[0], json.loads(row[1]))
            except (sqlite3.Error, ValueError) as e:
                self._degrade(e)
                return None
        # Treat an expired entry as missing (the caller re-checks the TTL too,
        # but this keeps get() consistent with len() before the next purge).
        if row is None or row[0] <= time.time():
            return None
        return row

    def __setitem__(self, key, entry) -> None:
        expires_at, value = entry
        key = self._key(key)
        if self._memory is not None:
            self._memory[key] = (expires_at, value)
            return
        try:
            # ASCII-escaped, so broken surrogates in Instagram text can't
            # fail the UTF-8 encoding of the SQLite TEXT column.
            payload = json.dumps(value)
        except (TypeError, ValueError):
            return  # unserializable response - just don't cache it
        try:
            with self._lock, self._db:
                self._db.execute(
                    "INSERT OR REPLACE INTO responses (key, expires_at, value) VALUES (?, ?, ?)",
                    (key, expires_at, payload),
                )
                self._writes += 1
            if self._writes % _PURGE_EVERY_WRITES == 0:
                self.purge_expired()
        except sqlite3.Error as e:
            self._degrade(e)
            self._memory[key] = (expires_at, value)

    def purge_expired(self) -> None:
        if self._memory is not None:
            now = time.time()
            self._memory = {k: v for k, v in self._memory.items() if v[0] > now}
            return
        try:
            with self._lock, self._db:
                self._db.execute("DELETE FROM responses WHERE expires_at <= ?", (time.time(),))
        except sqlite3.Error as e:
            self._degrade(e)

    def clear(self) -> int:
        """Delete every cached response; returns how many there were."""
        if self._memory is not None:
            n = len(self._memory)
            self._memory = {}
            return n
        try:
            with self._lock, self._db:
                return self._db.execute("DELETE FROM responses").rowcount
        except sqlite3.Error as e:
            self._degrade(e)
            return 0

    def __len__(self) -> int:
        now = time.time()
        if self._memory is not None:
            return sum(1 for v in self._memory.values() if v[0] > now)
        try:
            with self._lock:
                return self._db.execute(
                    "SELECT COUNT(*) FROM responses WHERE expires_at > ?", (now,)
                ).fetchone()[0]
        except sqlite3.Error as e:
            self._degrade(e)
            return 0
