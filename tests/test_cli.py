"""Tests for the Osintgram Headless CLI & Scheduled Audits engine."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.cli import (
    build_parser,
    execute_single_run,
    handle_snapshot_and_diff,
    handle_webhook_alert,
    main,
    resolve_commands,
    PRESETS,
)
from src.dossier_report import generate_html_report, generate_markdown_report


def test_cli_parser_options():
    parser = build_parser()
    args = parser.parse_args(["target_user", "-p", "audit", "--limit", "50", "--dossier", "--export-json", "out.json"])
    assert args.target_pos == "target_user"
    assert args.preset == "audit"
    assert args.limit == 50
    assert args.dossier is True
    assert args.export_json == "out.json"


def test_resolve_commands_preset_and_custom():
    assert resolve_commands("profile", None) == PRESETS["profile"]
    assert resolve_commands("network", None) == PRESETS["network"]
    custom = resolve_commands("profile", "get_user_info, get_hashtags , get_addrs")
    assert custom == ["get_user_info", "get_hashtags", "get_addrs"]


def test_cli_missing_target_returns_error(capsys):
    ret = main([])
    assert ret == 1
    err = capsys.readouterr().err
    assert "TARGET username is required" in err


def test_execute_single_run_mocked(monkeypatch):
    class FakeService:
        def __init__(self, target, **kw):
            self.target = target

        def get_user_info(self):
            return {"username": self.target, "follower_count": 100, "media_count": 10}

        def get_highlights(self):
            return [{"id": "h1", "title": "Trip"}]

    monkeypatch.setattr("src.cli.build_service", lambda target, backend=None: FakeService(target))

    run = execute_single_run("sample_target", ["get_user_info", "get_highlights"], quiet=True)
    assert run["target"] == "sample_target"
    assert run["mode"] == "headless_cli"
    assert len(run["results"]) == 2
    assert run["results"][0]["name"] == "get_user_info"
    assert run["results"][0]["result"]["follower_count"] == 100
    assert run["results"][1]["name"] == "get_highlights"


def test_dossier_report_generators():
    sample_data = {
        "id": "test-1234",
        "target": "alice_travel",
        "saved_at": 1700000000,
        "results": [
            {
                "name": "get_user_info",
                "result": {
                    "username": "alice_travel",
                    "full_name": "Alice Walker",
                    "follower_count": 4200,
                    "following_count": 350,
                    "media_count": 75,
                    "biography": "Travel photographer in Italy",
                    "is_verified": False,
                    "is_private": False,
                },
            },
            {
                "name": "get_hashtags",
                "result": [
                    {"hashtag": "#travel", "count": 15},
                    {"hashtag": "#italy", "count": 12},
                ],
            },
        ],
        "diff": {
            "has_changes": True,
            "summary": ["Bio changed", "2 new followers detected"],
        },
    }

    # Test Markdown report
    md = generate_markdown_report(sample_data)
    assert "# 🔎 OSINT Investigation Report: @alice_travel" in md
    assert "Alice Walker" in md
    assert "4,200" in md
    assert "Bio changed" in md
    assert "#travel" in md

    # Test HTML report
    html_rep = generate_html_report(sample_data)
    assert "<!DOCTYPE html>" in html_rep
    assert "@alice_travel" in html_rep
    assert "Travel photographer in Italy" in html_rep
    assert "Bio changed" in html_rep
    assert "#travel" in html_rep


def test_cli_exports_json_html_md(tmp_path, monkeypatch):
    class FakeService:
        def __init__(self, target, **kw):
            self.target = target

        def get_user_info(self):
            return {"username": self.target, "follower_count": 500}

    monkeypatch.setattr("src.cli.build_service", lambda target, backend=None: FakeService(target))

    json_file = tmp_path / "report.json"
    html_file = tmp_path / "report.html"
    md_file = tmp_path / "report.md"

    argv = [
        "target_user",
        "-c", "get_user_info",
        "--export-json", str(json_file),
        "--export-html", str(html_file),
        "--export-md", str(md_file),
        "-q",
    ]
    ret = main(argv)
    assert ret == 0

    assert json_file.exists()
    assert html_file.exists()
    assert md_file.exists()

    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["target"] == "target_user"
    assert "target_user" in html_file.read_text(encoding="utf-8")
    assert "target_user" in md_file.read_text(encoding="utf-8")


def test_cli_dossier_save_and_list(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("src.web.dossier.DOSSIER_DIR", tmp_path / "dossiers")

    class FakeService:
        def __init__(self, target, **kw):
            self.target = target

        def get_user_info(self):
            return {"username": self.target}

    monkeypatch.setattr("src.cli.build_service", lambda target, backend=None: FakeService(target))

    # Run with --dossier
    ret1 = main(["agent_zero", "-c", "get_user_info", "--dossier", "-q"])
    assert ret1 == 0

    # List dossiers
    ret2 = main(["--list-dossiers"])
    assert ret2 == 0
    out = capsys.readouterr().out
    assert "Saved dossiers" in out
    assert "@agent_zero" in out


def test_cli_compare_dossiers(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("src.web.dossier.DOSSIER_DIR", tmp_path / "dossiers")

    import src.web.dossier as dmod
    d1_summary = dmod.save({
        "target": "target_x",
        "results": [{"name": "get_user_info", "result": {"follower_count": 100}}],
    })
    d2_summary = dmod.save({
        "target": "target_x",
        "results": [{"name": "get_user_info", "result": {"follower_count": 115}}],
    })

    ret = main(["-t", "target_x", "--compare", d1_summary["id"], d2_summary["id"]])
    assert ret == 0
    out = capsys.readouterr().out
    diff = json.loads(out)
    assert diff["target"] == "target_x"
    assert any(c["name"] == "get_user_info" for c in diff["commands"])


def test_cli_webhook_alert(monkeypatch):
    dispatched = []

    def mock_dispatch(**kw):
        dispatched.append(kw)
        return True

    monkeypatch.setattr("src.webhook_dispatcher.dispatch_webhook", mock_dispatch)

    run_data = {"target": "monitored_user", "results": [{"name": "get_user_info"}]}
    diff_data = {"has_changes": True, "summary": ["Bio modified"]}

    ok = handle_webhook_alert(
        webhook_url="https://discord.com/api/webhooks/123/xyz",
        target="monitored_user",
        diff_data=diff_data,
        run_data=run_data,
        quiet=True,
    )
    assert ok is True
    assert len(dispatched) == 1
    assert dispatched[0]["target"] == "monitored_user"
    assert dispatched[0]["event_type"] == "profile_diff"


def test_cli_watch_mode_iterations(monkeypatch):
    class FakeService:
        def __init__(self, target, **kw):
            self.target = target

        def get_user_info(self):
            return {"username": self.target}

    monkeypatch.setattr("src.cli.build_service", lambda target, backend=None: FakeService(target))

    sleep_calls = []
    monkeypatch.setattr("time.sleep", lambda secs: sleep_calls.append(secs))

    # Run with watch interval = 0.5 min, iterations = 2
    ret = main(["watch_target", "-c", "get_user_info", "--watch", "0.5", "--iterations", "2", "-q"])
    assert ret == 0
    # Should sleep once between iteration 1 and 2
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 30.0
