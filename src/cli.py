"""Headless CLI & Scheduled Audit Engine for Osintgram.

Enables automated investigations, CI/CD audit pipelines, headless dossier
generation, periodic target tracking, and webhook alert notifications.
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.osint_service import OsintServiceError, build_service
from src.dossier_report import generate_html_report, generate_markdown_report
import src.web.dossier as dossier

logger = logging.getLogger("osintgram.cli")

PRESETS: Dict[str, List[str]] = {
    "profile": ["get_user_info", "get_account_about", "get_highlights"],
    "network": ["get_followers", "get_followings", "get_suggested_profiles"],
    "content": [
        "get_hashtags",
        "get_captions",
        "get_addrs",
        "get_total_likes",
        "get_total_comments",
        "get_media_type",
        "get_posting_times",
    ],
    "audit": ["get_user_info", "get_account_about", "get_followers", "get_followings"],
    "full": [
        "get_user_info",
        "get_account_about",
        "get_highlights",
        "get_hashtags",
        "get_captions",
        "get_addrs",
        "get_total_likes",
        "get_total_comments",
        "get_media_type",
        "get_posting_times",
        "get_followers",
        "get_followings",
    ],
}


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser for Osintgram headless operations."""
    parser = argparse.ArgumentParser(
        prog="osintgram",
        description="Osintgram Headless CLI — Automated OSINT Audits & Investigations",
    )

    parser.add_argument(
        "target_pos",
        nargs="?",
        metavar="TARGET",
        help="Target Instagram username (e.g. 'instagram' or '@target')",
    )
    parser.add_argument(
        "-t", "--target",
        dest="target_opt",
        help="Target Instagram username (alternative flag)",
    )
    parser.add_argument(
        "-c", "--command", "--commands",
        dest="commands",
        help="Comma-separated list of commands to run (e.g. 'get_user_info,get_followers')",
    )
    parser.add_argument(
        "-p", "--preset",
        choices=list(PRESETS.keys()),
        default="profile",
        help="Predefined command preset to run (default: profile)",
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=200,
        help="Maximum items to fetch for follower/following/media scans (default: 200)",
    )
    parser.add_argument(
        "--limit-posts",
        type=int,
        default=None,
        help="Maximum posts to scan for captions, hashtags, and locations",
    )
    parser.add_argument(
        "--dossier",
        action="store_true",
        help="Save completed run as an investigation dossier in dossier/ folder",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Record target state as a profile snapshot in the local tracker DB",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Compute and display diff against previous snapshot or dossier",
    )
    parser.add_argument(
        "--export-json",
        metavar="PATH",
        help="Export full audit results to a JSON file",
    )
    parser.add_argument(
        "--export-html",
        metavar="PATH",
        help="Generate and export a standalone, self-contained HTML dossier report",
    )
    parser.add_argument(
        "--export-md", "--export-markdown",
        dest="export_md",
        metavar="PATH",
        help="Export a structured Markdown investigation report",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("DOSSIER1", "DOSSIER2"),
        help="Compare two saved dossier IDs and show changes",
    )
    parser.add_argument(
        "--list-dossiers",
        action="store_true",
        help="List saved investigation dossiers for target or all targets",
    )
    parser.add_argument(
        "--watch", "--schedule",
        dest="schedule_interval",
        type=float,
        default=None,
        metavar="MINUTES",
        help="Run continuously on a recurring schedule every N minutes",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Number of scheduled iterations to perform (default: 1, or infinite if watch set)",
    )
    parser.add_argument(
        "--webhook",
        metavar="URL",
        help="Webhook URL (Discord, Slack, Telegram, or generic) to alert on diff/completion",
    )
    parser.add_argument(
        "--telegram-chat-id",
        help="Chat ID required for Telegram Bot API webhook alerts",
    )
    parser.add_argument(
        "--backend",
        choices=["hikerapi", "instagrapi"],
        default=None,
        help="Explicitly override the Instagram backend (default: auto-detect)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Quiet mode: suppress banners, progress bars, and log details",
    )

    return parser


def resolve_commands(preset: str, explicit_commands: Optional[str]) -> List[str]:
    """Resolve which commands to execute based on flags."""
    if explicit_commands:
        cmds = [c.strip() for c in explicit_commands.split(",") if c.strip()]
        if cmds:
            return cmds
    return PRESETS.get(preset, PRESETS["profile"])


def execute_single_run(
    target: str,
    commands: List[str],
    limit: int = 200,
    limit_posts: Optional[int] = None,
    backend: Optional[str] = None,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Execute the selected Osintgram commands for a target and return the results."""
    service = build_service(target, backend=backend)
    results = []

    for cmd in commands:
        if not hasattr(service, cmd):
            if not quiet:
                print(f"[!] Warning: Command '{cmd}' is not recognized on OsintgramService; skipping.", file=sys.stderr)
            continue

        method = getattr(service, cmd)
        if not quiet:
            print(f"[*] Running: {cmd}...", file=sys.stderr)

        start_time = time.time()
        try:
            # Check parameter support
            import inspect
            sig = inspect.signature(method)
            kwargs = {}
            if "limit" in sig.parameters:
                kwargs["limit"] = limit
            if "limit_posts" in sig.parameters:
                kwargs["limit_posts"] = limit_posts

            res = method(**kwargs)
            results.append({
                "name": cmd,
                "result": res,
                "elapsed_ms": int((time.time() - start_time) * 1000),
            })
        except Exception as e:
            if not quiet:
                print(f"[!] Error in {cmd}: {e}", file=sys.stderr)
            results.append({
                "name": cmd,
                "error": str(e),
                "elapsed_ms": int((time.time() - start_time) * 1000),
            })

    run_data: Dict[str, Any] = {
        "target": target,
        "mode": "headless_cli",
        "saved_at": int(time.time()),
        "commands": commands,
        "results": results,
    }
    return run_data


def handle_snapshot_and_diff(
    target: str, run_data: dict, quiet: bool = False
) -> Optional[dict]:
    """Record a snapshot and/or compute diff against latest prior state."""
    from src.snapshot_tracker import (
        create_snapshot,
        diff_latest_two,
    )

    profile_data = None
    followers = None
    followings = None

    for r in run_data.get("results") or []:
        name = r.get("name")
        res = r.get("result")
        if name == "get_user_info" and isinstance(res, dict):
            profile_data = res
        elif name == "get_followers" and isinstance(res, list):
            followers = res
        elif name == "get_followings" and isinstance(res, list):
            followings = res

    if profile_data:
        try:
            create_snapshot(target, profile_data, followers=followers, followings=followings)
            if not quiet:
                print(f"[+] Snapshot saved to local database for @{target}.", file=sys.stderr)
        except Exception as e:
            if not quiet:
                print(f"[!] Could not save snapshot: {e}", file=sys.stderr)

    try:
        diff_res = diff_latest_two(target)
        if diff_res and diff_res.get("has_changes"):
            run_data["diff"] = diff_res
            if not quiet:
                print(f"[!] Profile changes detected for @{target}:", file=sys.stderr)
                for line in diff_res.get("summary", []):
                    print(f"    - {line}", file=sys.stderr)
            return diff_res
    except Exception:
        pass

    return None


def handle_webhook_alert(
    webhook_url: str,
    target: str,
    diff_data: Optional[dict],
    run_data: dict,
    chat_id: Optional[str] = None,
    quiet: bool = False,
) -> bool:
    """Dispatch webhook alert if changes are detected or run completed."""
    from src.webhook_dispatcher import dispatch_webhook

    event_type = "profile_diff" if diff_data and diff_data.get("has_changes") else "audit_completed"
    payload_data = diff_data if event_type == "profile_diff" else {
        "summary": [f"Completed audit for @{target} ({len(run_data.get('results', []))} commands)."],
        "target": target,
        "has_changes": False,
    }

    try:
        ok = dispatch_webhook(
            webhook_url=webhook_url,
            event_type=event_type,
            data=payload_data,
            target=target,
            chat_id=chat_id,
        )
        if ok and not quiet:
            print(f"[+] Webhook notification successfully sent to {webhook_url[:20]}...", file=sys.stderr)
        return ok
    except Exception as e:
        if not quiet:
            print(f"[!] Failed to deliver webhook: {e}", file=sys.stderr)
        return False


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # 1. Compare dossiers mode
    if args.compare:
        id1, id2 = args.compare
        d1 = dossier.load(args.target_opt or args.target_pos or "", id1) or json.loads(Path(id1).read_text(encoding="utf-8"))
        d2 = dossier.load(args.target_opt or args.target_pos or "", id2) or json.loads(Path(id2).read_text(encoding="utf-8"))
        diff = dossier.compare(d1, d2)
        print(json.dumps(diff, ensure_ascii=False, indent=2))
        return 0

    # 2. List dossiers mode
    if args.list_dossiers:
        target = (args.target_opt or args.target_pos or "").strip().lstrip("@") or None
        dossiers = dossier.list_for(target)
        if args.quiet:
            print(json.dumps(dossiers, ensure_ascii=False, indent=2))
        else:
            if not dossiers:
                print("No saved dossiers found.")
            else:
                print(f"Saved dossiers ({len(dossiers)} total):")
                for d in dossiers:
                    print(f"  - [{d.get('id')}] @{d.get('target')} ({time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(d.get('saved_at', 0)))}) | {len(d.get('commands', []))} commands")
        return 0

    # Target resolution
    target = (args.target_opt or args.target_pos or "").strip().lstrip("@")
    if not target:
        parser.print_help(sys.stderr)
        print("\n[!] Error: TARGET username is required.", file=sys.stderr)
        return 1

    commands = resolve_commands(args.preset, args.commands)
    interval = args.schedule_interval
    iterations = args.iterations or (1 if interval is None else 999999)

    if not args.quiet:
        print(f"🔎 Osintgram Headless CLI & Audit Engine")
        print(f"Target: @{target} | Preset/Commands: {len(commands)} selected | Backend: {args.backend or 'auto'}")
        if interval:
            print(f"Scheduled Watch Mode: Every {interval} minutes ({iterations} iterations)")
        print("-" * 60, file=sys.stderr)

    current_iter = 0
    while current_iter < iterations:
        current_iter += 1
        if not args.quiet and interval and current_iter > 1:
            print(f"\n[*] Starting scheduled audit #{current_iter} for @{target}...", file=sys.stderr)

        try:
            run_data = execute_single_run(
                target=target,
                commands=commands,
                limit=args.limit,
                limit_posts=args.limit_posts,
                backend=args.backend,
                quiet=args.quiet,
            )
        except OsintServiceError as e:
            print(f"[!] Osintgram Service Error: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"[!] Unexpected error during run: {e}", file=sys.stderr)
            return 3

        # Snapshot and Diff handling
        diff_data = None
        if args.snapshot or args.diff:
            diff_data = handle_snapshot_and_diff(target, run_data, quiet=args.quiet)

        # Webhook notifications
        if args.webhook:
            handle_webhook_alert(
                webhook_url=args.webhook,
                target=target,
                diff_data=diff_data,
                run_data=run_data,
                chat_id=args.telegram_chat_id,
                quiet=args.quiet,
            )

        # Dossier save
        if args.dossier:
            summary = dossier.save(run_data)
            run_data["id"] = summary.get("id")
            if not args.quiet:
                print(f"[+] Saved dossier #{summary.get('id')} to dossier/{target}/", file=sys.stderr)

        # File exports
        if args.export_json:
            out_p = Path(args.export_json)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(json.dumps(run_data, ensure_ascii=False, indent=2), encoding="utf-8")
            if not args.quiet:
                print(f"[+] Exported JSON report to {args.export_json}", file=sys.stderr)

        if args.export_html:
            html_content = generate_html_report(run_data)
            out_p = Path(args.export_html)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(html_content, encoding="utf-8")
            if not args.quiet:
                print(f"[+] Exported HTML dossier to {args.export_html}", file=sys.stderr)

        if args.export_md:
            md_content = generate_markdown_report(run_data)
            out_p = Path(args.export_md)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(md_content, encoding="utf-8")
            if not args.quiet:
                print(f"[+] Exported Markdown dossier to {args.export_md}", file=sys.stderr)

        # Terminal output (if not exporting or if quiet JSON output requested)
        if args.quiet:
            print(json.dumps(run_data, ensure_ascii=False))
        elif not (args.export_json or args.export_html or args.export_md):
            print(json.dumps(run_data, ensure_ascii=False, indent=2))

        # Sleep if scheduled watch mode
        if interval and current_iter < iterations:
            if not args.quiet:
                print(f"[*] Sleeping for {interval} minutes until next scheduled audit...", file=sys.stderr)
            time.sleep(interval * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
