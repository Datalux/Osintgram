"""Universal Webhook Dispatcher for Osintgram.

Supports Discord Webhooks, Slack Webhooks, Telegram Bot API, and generic
JSON webhooks (e.g. for n8n, Make, or custom SIEM collectors).
"""
import json
import logging
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)


def build_discord_payload(target: str, diff_data: Dict[str, Any]) -> Dict[str, Any]:
    """Format snapshot difference data into a rich Discord webhook embed."""
    summary_lines = diff_data.get("summary") or ["No notable changes detected."]
    desc = "\n".join(f"• {line}" for line in summary_lines)

    fields = []
    deltas = diff_data.get("metric_deltas") or {}
    if deltas:
        fol = deltas.get("followers", {})
        diff_str = f"{fol.get('diff', 0):+,}" if fol.get("diff") else "0"
        fields.append({
            "name": "👥 Followers",
            "value": f"{fol.get('old', 0):,} → {fol.get('new', 0):,} ({diff_str})",
            "inline": True,
        })
        fing = deltas.get("following", {})
        diff_fing = f"{fing.get('diff', 0):+,}" if fing.get("diff") else "0"
        fields.append({
            "name": "🔗 Following",
            "value": f"{fing.get('old', 0):,} → {fing.get('new', 0):,} ({diff_fing})",
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

    embed = {
        "title": f"🔔 Profile Change Detected: @{target}",
        "url": f"https://www.instagram.com/{target}/",
        "color": 0xE1306C if diff_data.get("has_changes") else 0x4F46E5,
        "description": desc,
        "fields": fields,
        "footer": {
            "text": "Osintgram Target Watcher • Snapshot Diff",
        },
    }
    return {
        "username": "Osintgram Watcher",
        "embeds": [embed],
    }


def build_slack_payload(target: str, diff_data: Dict[str, Any]) -> Dict[str, Any]:
    """Format snapshot difference data into Slack Block Kit format."""
    summary_lines = diff_data.get("summary") or ["No notable changes detected."]
    bullet_text = "\n".join(f"• {line}" for line in summary_lines)

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🔔 Profile Change: @{target}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Instagram:* <https://instagram.com/{target}|@{target}>\n\n{bullet_text}",
            },
        },
    ]
    return {"blocks": blocks}


def build_telegram_payload(target: str, diff_data: Dict[str, Any], chat_id: Optional[str] = None) -> Dict[str, Any]:
    """Format snapshot difference data into HTML message for Telegram Bot API."""
    summary_lines = diff_data.get("summary") or ["No notable changes detected."]
    bullet_text = "\n".join(f"• {line}" for line in summary_lines)

    text = (
        f"🔔 <b>Profile Change Detected: @{target}</b>\n"
        f"🔗 <a href='https://instagram.com/{target}'>instagram.com/{target}</a>\n\n"
        f"<b>Changes summary:</b>\n{bullet_text}"
    )
    payload: Dict[str, Any] = {
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if chat_id:
        payload["chat_id"] = chat_id
    return payload


def dispatch_webhook(
    webhook_url: str,
    event_type: str,
    data: Dict[str, Any],
    target: str = "",
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Send webhook payload formatted for Discord, Slack, Telegram, or generic JSON."""
    url = (webhook_url or "").strip()
    if not url:
        return {"ok": False, "error": "Webhook URL is empty."}

    # Auto-detect webhook provider
    url_lower = url.lower()
    if "discord.com/api/webhooks" in url_lower:
        payload = build_discord_payload(target or data.get("target", "target"), data)
    elif "hooks.slack.com" in url_lower:
        payload = build_slack_payload(target or data.get("target", "target"), data)
    elif "api.telegram.org/bot" in url_lower:
        payload = build_telegram_payload(target or data.get("target", "target"), data)
    else:
        # Generic JSON payload (compatible with n8n, Make, custom webhooks)
        payload = {
            "event": event_type,
            "target": target or data.get("target", "target"),
            "data": data,
        }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers={"User-Agent": "Osintgram-Webhook/2.0"})
            is_ok = 200 <= resp.status_code < 300
            return {
                "ok": is_ok,
                "status_code": resp.status_code,
                "response": resp.text[:200] if not is_ok else "ok",
            }
    except Exception as e:
        logger.warning(f"Webhook dispatch failed to {url}: {e}")
        return {
            "ok": False,
            "status_code": 0,
            "error": str(e),
        }
