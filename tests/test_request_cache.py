"""Tests for the disk-backed request cache (src/web/request_cache.py)."""
import time

from src.web.request_cache import PersistentRequestCache

KEY = ("user_by_id_v2", ("123",), ())


def test_get_set_and_expiry(tmp_path):
    c = PersistentRequestCache(tmp_path / "cache" / "r.sqlite3")
    c[KEY] = (time.time() + 60, {"user": {"n": 1}})
    assert c.get(KEY)[1] == {"user": {"n": 1}}
    c[("x", (), ())] = (time.time() - 1, {"old": True})  # already expired
    assert c.get(("x", (), ())) is None  # expired -> treated as missing
    assert len(c) == 1


def test_survives_reopen(tmp_path):
    path = tmp_path / "r.sqlite3"
    c = PersistentRequestCache(path)
    c[KEY] = (time.time() + 60, {"n": 2})
    reopened = PersistentRequestCache(path)  # "restart"
    assert reopened.get(KEY)[1] == {"n": 2}


def test_unserializable_value_is_skipped(tmp_path):
    c = PersistentRequestCache(tmp_path / "r.sqlite3")
    c[KEY] = (time.time() + 60, {"obj": object()})
    assert c.get(KEY) is None


def test_broken_surrogates_do_not_raise(tmp_path):
    c = PersistentRequestCache(tmp_path / "r.sqlite3")
    c[KEY] = (time.time() + 60, {"bio": "ok \ud83d broken"})  # lone surrogate from IG data
    assert "broken" in c.get(KEY)[1]["bio"]


def test_clear(tmp_path):
    c = PersistentRequestCache(tmp_path / "r.sqlite3")
    c[KEY] = (time.time() + 60, {"n": 1})
    assert c.clear() == 1
    assert len(c) == 0


def test_write_failure_degrades_to_memory_without_raising(tmp_path):
    c = PersistentRequestCache(tmp_path / "r.sqlite3")
    c._db.close()  # simulate the DB becoming unusable (e.g. its dir was removed)
    c[KEY] = (time.time() + 60, {"n": 7})  # must not raise
    assert c._memory is not None  # fell back to in-memory
    assert c.get(KEY)[1] == {"n": 7}  # still cached, in memory
    assert len(c) == 1


def test_unwritable_path_still_constructs_and_works(tmp_path):
    # A path that can't be created as a database (a directory in the way)
    # must not crash construction - it degrades to memory.
    (tmp_path / "busy").mkdir()
    c = PersistentRequestCache(tmp_path / "busy")
    c[KEY] = (time.time() + 60, {"n": 1})
    assert c.get(KEY)[1] == {"n": 1}
