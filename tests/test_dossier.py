"""Tests for saved searches and the change comparison (src/web/dossier.py)."""
import pytest

from src.web import dossier


@pytest.fixture(autouse=True)
def _tmp_dossier_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dossier, "DOSSIER_DIR", tmp_path / "dossier")


def run(target="alice", results=None, saved_at=None, **extra):
    r = {"target": target, "mode": "base", "results": results or [], **extra}
    if saved_at is not None:
        r["saved_at"] = saved_at
    return r


def test_save_list_load_delete():
    saved = dossier.save(run(results=[{"name": "get_user_info", "result": {"follower_count": 10}}]))
    assert saved["target"] == "alice" and saved["commands"] == ["get_user_info"]
    listed = dossier.list_for("alice")
    assert [s["id"] for s in listed] == [saved["id"]]
    assert dossier.load("alice", saved["id"])["results"][0]["name"] == "get_user_info"
    assert dossier.delete("alice", saved["id"]) is True
    assert dossier.list_for("alice") == []


def test_two_saves_in_the_same_second_do_not_overwrite():
    a = dossier.save(run("alice", results=[{"name": "x", "result": 1}]))
    b = dossier.save(run("alice", results=[{"name": "x", "result": 2}]))
    assert a["id"] != b["id"]
    assert len(dossier.list_for("alice")) == 2


def test_list_is_newest_first_and_can_span_targets():
    a = dossier.save(run("alice"))
    b = dossier.save(run("bob"))
    for s in (a, b):
        assert s["id"]
    every = dossier.list_for()
    assert {s["target"] for s in every} == {"alice", "bob"}
    assert every == sorted(every, key=lambda s: s["saved_at"], reverse=True)


def test_username_cannot_escape_the_dossier_directory():
    saved = dossier.save(run("../../etc/passwd"))
    assert dossier.load("../../etc/passwd", saved["id"]) is not None
    # Everything stays inside DOSSIER_DIR.
    assert all(dossier.DOSSIER_DIR in p.parents for p in dossier.DOSSIER_DIR.rglob("*.json"))


def test_a_bare_double_dot_target_does_not_escape_either():
    """A multi-segment payload ("../../etc/passwd") gets its slashes replaced
    and is already covered above - but ".." on its own is made entirely of
    characters _safe()'s regex allows (dots), so it survives that
    substitution untouched and is a path segment meaning "parent directory"
    in its own right. Saving one must not write outside DOSSIER_DIR."""
    parent_before = set(dossier.DOSSIER_DIR.parent.iterdir())

    saved = dossier.save(run(".."))

    parent_after = set(dossier.DOSSIER_DIR.parent.iterdir())
    # Nothing new appeared next to (i.e. one level above) DOSSIER_DIR...
    assert parent_after - parent_before <= {dossier.DOSSIER_DIR}
    # ...and the file is exactly where a same-directory save would put it.
    assert dossier.load("..", saved["id"]) is not None
    assert all(dossier.DOSSIER_DIR in p.parents for p in dossier.DOSSIER_DIR.rglob("*.json"))


def test_a_bare_double_dot_id_does_not_escape_either():
    saved_at = dossier.save(run("alice"))
    escaped = dossier._path("alice", "..")
    assert dossier.DOSSIER_DIR in escaped.parents
    assert escaped.name != ".."


def test_deleting_a_bare_double_dot_target_cannot_remove_a_file_above_dossier_dir():
    sentinel = dossier.DOSSIER_DIR.parent / "sentinel.json"
    sentinel.write_text("{}")
    dossier.save(run(".."))  # lands inside DOSSIER_DIR/_, not next to it

    dossier.delete("..", "whatever-id-does-not-even-need-to-exist")

    assert sentinel.exists()  # untouched: delete() could never have reached it


def test_a_lone_dot_target_does_not_collapse_into_dossier_dir_itself():
    """"." is "this directory" - as the whole target it would make _path()
    write straight into DOSSIER_DIR (no per-target subfolder at all), not
    escape it, but it's the same class of mistake as ".." and just as easy
    to rule out at no cost."""
    assert dossier._safe(".") != "."


def test_load_missing_returns_none():
    assert dossier.load("alice", "nope") is None


def test_compare_reports_added_and_removed_followers():
    before = run(results=[{"name": "get_followers", "result": [
        {"id": "1", "username": "anna"}, {"id": "2", "username": "bruno"}]}], saved_at=100)
    after = run(results=[{"name": "get_followers", "result": [
        {"id": "2", "username": "bruno"}, {"id": "3", "username": "carla"}]}], saved_at=200)
    diff = dossier.compare(before, after)
    entry = diff["commands"][0]
    assert entry["added"] == ["carla"]
    assert entry["removed"] == ["anna"]
    assert entry["count_before"] == 2 and entry["count_after"] == 2
    assert entry["unchanged"] is False


def test_compare_reports_changed_profile_fields():
    before = run(results=[{"name": "get_user_info", "result": {"follower_count": 10, "biography": "ciao"}}], saved_at=1)
    after = run(results=[{"name": "get_user_info", "result": {"follower_count": 12, "biography": "nuova bio"}}], saved_at=2)
    changes = {c["field"]: (c["from"], c["to"]) for c in dossier.compare(before, after)["commands"][0]["changed"]}
    assert changes["follower_count"] == (10, 12)
    assert changes["biography"] == ("ciao", "nuova bio")


def test_compare_ignores_volatile_media_urls():
    # Signed CDN URLs change on every fetch - reporting them would be noise.
    before = run(results=[{"name": "get_user_propic", "result": {"url": "https://cdn/a.jpg?sig=1"}}], saved_at=1)
    after = run(results=[{"name": "get_user_propic", "result": {"url": "https://cdn/a.jpg?sig=2"}}], saved_at=2)
    assert dossier.compare(before, after)["commands"][0]["unchanged"] is True


def test_compare_marks_unchanged_commands():
    same = [{"name": "get_followers", "result": [{"id": "1", "username": "anna"}]}]
    diff = dossier.compare(run(results=same, saved_at=1), run(results=same, saved_at=2))
    assert diff["commands"][0]["unchanged"] is True


def test_compare_lists_commands_present_in_only_one_run():
    before = run(results=[{"name": "get_followers", "result": []}], saved_at=1)
    after = run(results=[{"name": "get_hashtags", "result": []}], saved_at=2)
    diff = dossier.compare(before, after)
    assert diff["only_in_before"] == ["get_followers"]
    assert diff["only_in_after"] == ["get_hashtags"]
    assert diff["commands"] == []


def test_compare_handles_nested_lists_inside_a_dict_result():
    before = run(results=[{"name": "get_photo_descriptions", "result": {
        "photos_scanned": 2, "descriptions": [{"description": "un gatto"}]}}], saved_at=1)
    after = run(results=[{"name": "get_photo_descriptions", "result": {
        "photos_scanned": 3, "descriptions": [{"description": "un gatto"}, {"description": "una bici"}]}}], saved_at=2)
    entry = dossier.compare(before, after)["commands"][0]
    assert entry["added"] == ["una bici"]
    assert {"field": "photos_scanned", "from": 2, "to": 3} in entry["changed"]
