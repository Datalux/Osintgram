"""Universal Webhook Dispatcher for Osintgram.

Supports Discord Webhooks, Slack Webhooks, Telegram Bot API, and generic
JSON webhooks (e.g. for n8n, Make, or custom SIEM collectors).
"""
import html
import ipaddress
import logging
import urllib.parse
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)


def mask_webhook_url(url: str) -> str:
    """Mask tokens in webhook URL for safe logging and error reports."""
    clean_url = (url or "").strip()
    if not clean_url:
        return ""
    try:
        p = urllib.parse.urlsplit(clean_url)
        parts = p.path.split("/")
        if len(parts) > 2:
            parts[-1] = "***"
            if len(parts) > 3 and "webhooks" in parts[1:3]:
                parts[-2] = "***"
        masked_path = "/".join(parts)
        return urllib.parse.urlunsplit(
            (p.scheme, p.netloc, masked_path, "", "")
        )
    except Exception:
        return (clean_url[:15] + "***") if len(clean_url) > 15 else "***"


def _escape_slack(text: str) -> str:
    """Escape control characters for Slack mrkdwn."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_discord_payload(
    target: str, diff_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Format snapshot difference data into a rich Discord webhook embed."""
    summary_lines = (
        diff_data.get("summary") or ["No notable changes detected."]
    )
    desc = "\n".join(f"• {line}" for line in summary_lines)

    fields = []
    deltas = diff_data.get("metric_deltas") or {}
    if deltas:
        fol = deltas.get("followers", {})
        diff_str = f"{fol.get('diff', 0):+,}" if fol.get("diff") else "0"
        fields.append({
            "name": "👥 Followers",
            "value": (
                f"{fol.get('old', 0):,} → {fol.get('new', 0):,} ({diff_str})"
            ),
            "inline": True,
        })
        fing = deltas.get("following", {})
        diff_fing = f"{fing.get('diff', 0):+,}" if fing.get("diff") else "0"
        fields.append({
            "name": "🔗 Following",
            "value": (
                f"{fing.get('old', 0):,} → {fing.get('new', 0):,} "
                f"({diff_fing})"
            ),
            "inline": True,
        })

    net = diff_data.get("network_changes") or {}
    if net.get("lost_followers"):
        fields.append({
            "name": f"📉 Unfollowers ({len(net['lost_followers'])})",
            "value": ", ".join(f"@{u}" for u in net["lost_followers"][:10]),
            "inline": False,
        })
    if net.get("new_followers"):
        fields.append({
            "name": f"📈 New Followers ({len(net['new_followers'])})",
            "value": ", ".join(f"@{u}" for u in net["new_followers"][:10]),
            "inline": False,
        })

    safe_target = target.strip().lstrip("@")
    embed = {
        "title": f"🔔 Profile Change Detected: @{safe_target}",
        "url": f"https://www.instagram.com/{safe_target}/",
        "color": 0xE1306C if diff_data.get("has_changes") else 0x4F46E5,
        "description": desc,
        "fields": fields,
        "footer": {
            "text": "Osintgram Profile Snapshot Diff",
        },
    }
    return {
        "username": "Osintgram Diff Tracker",
        "embeds": [embed],
    }


def build_slack_payload(
    target: str, diff_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Format snapshot difference data into Slack Block Kit format."""
    summary_lines = (
        diff_data.get("summary") or ["No notable changes detected."]
    )
    bullet_text = "\n".join(
        f"• {_escape_slack(line)}" for line in summary_lines
    )
    safe_target = _escape_slack(target.strip().lstrip("@"))

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🔔 Profile Change: @{safe_target}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Instagram:* <https://instagram.com/{safe_target}"
                    f"|@{safe_target}>\n\n{bullet_text}"
                ),
            },
        },
    ]
    return {"blocks": blocks}


def build_telegram_payload(
    target: str,
    diff_data: Dict[str, Any],
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Format snapshot difference data into HTML message for Telegram Bot."""
    summary_lines = (
        diff_data.get("summary") or ["No notable changes detected."]
    )
    bullet_text = "\n".join(f"• {html.escape(line)}" for line in summary_lines)
    safe_target = html.escape(target.strip().lstrip("@"))

    text = (
        f"🔔 <b>Profile Change Detected: @{safe_target}</b>\n"
        f"🔗 <a href='https://instagram.com/{safe_target}'>"
        f"instagram.com/{safe_target}</a>\n\n"
        f"<b>Changes summary:</b>\n{bullet_text}"
    )
    payload: Dict[str, Any] = {
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if chat_id:
        payload["chat_id"] = str(chat_id).strip()
    return payload


def dispatch_webhook(
    webhook_url: str,
    event_type: str,
    data: Dict[str, Any],
    target: str = "",
    chat_id: Optional[str] = None,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Send webhook payload formatted for Discord, Slack, Telegram, or JSON."""
    url = (webhook_url or "").strip()
    if not url:
        return {"ok": False, "error": "Webhook URL is empty."}

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != "https":
        return {
            "ok": False,
            "error": "Only https:// webhook URLs are allowed.",
        }

    hostname = (parsed.hostname or "").lower()
    blocked_hosts = ("localhost", "127.0.0.1", "::1")
    if (
        not hostname
        or hostname in blocked_hosts
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        return {
            "ok": False,
            "error": "Private and loopback addresses are blocked.",
        }

    try:
        ip = ipaddress.ip_address(hostname)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_reserved
            or ip.is_link_local
        ):
            return {
                "ok": False,
                "error": "Private and loopback IP addresses are blocked.",
            }
    except ValueError:
        pass

    # Compare host for provider detection
    host = hostname
    target_clean = target or data.get("target", "target")

    discord_hosts = ("discord.com", "discordapp.com")
    if host in discord_hosts or host.endswith(".discord.com"):
        payload = build_discord_payload(target_clean, data)
    elif host == "hooks.slack.com" or host.endswith(".slack.com"):
        payload = build_slack_payload(target_clean, data)
    elif host == "api.telegram.org" or host.endswith(".telegram.org"):
        payload = build_telegram_payload(
            target_clean, data, chat_id=chat_id
        )
    else:
        # Generic JSON payload (compatible with n8n, Make, custom webhooks)
        payload = {
            "event": event_type,
            "target": target_clean,
            "data": data,
        }

    masked_url = mask_webhook_url(url)
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                url,
                json=payload,
                headers={"User-Agent": "Osintgram-Webhook/2.0"},
            )
            is_ok = 200 <= resp.status_code < 300
            return {
                "ok": is_ok,
                "status_code": resp.status_code,
                "response": resp.text[:200] if not is_ok else "ok",
            }
    except Exception as e:
        logger.warning(f"Webhook dispatch failed to {masked_url}: {e}")
        return {
            "ok": False,
            "error": f"Webhook dispatch failed: {type(e).__name__}",
        }
