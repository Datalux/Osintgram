"""Bot and Anomaly Detector for Instagram Audience Audit.

Analyzes a collection of followers for fake, bot, and suspicious accounts
using deterministic heuristics:
- Avatar status (placeholder/anonymous profile picture vs custom avatar)
- Handle characteristics (digit ratio, trailing numbers, entropy, bot keywords)
- Full name patterns (blank name, repetitive strings, spam/crypto keywords)
- Credibility markers (verified accounts, engagement)

Outputs a comprehensive audit report with an authenticity rating,
risk breakdown, and identified suspicious profiles.
Scores are heuristic triage indicators, not definitive verdicts.
"""
import math
import re
from typing import Any, Dict, List, Optional, Tuple

# Common spam/scam/bot keywords found in usernames or full names
SPAM_KEYWORDS = {
    "crypto", "bitcoin", "btc", "forex", "trading", "investment",
    "dm for promo", "promo", "boost", "followers", "giveaway", "free followers",
    "earn $", "telegram", "whatsapp", "sugar daddy", "cashapp", "onlyfans",
    "dating", "hookup", "escort", "binance", "passive income", "airdrop"
}

# Regex for trailing numbers (e.g. user9841824 or mark_284192)
TRAILING_DIGITS_RE = re.compile(r"(\d{3,})$")

# Known default avatar URL substrings used by Instagram CDN
DEFAULT_AVATAR_SUBSTRINGS = (
    "44884218_345707102882519",
    "default_profile_pic",
    "default_avatar",
    "anonymous_profile",
)


def _calculate_entropy(text: str) -> float:
    """Shannon entropy of a string (higher = more random/gibberish)."""
    if not text:
        return 0.0
    text_len = len(text)
    counts: Dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    entropy = 0.0
    for count in counts.values():
        p = count / text_len
        entropy -= p * math.log2(p)
    return entropy


def evaluate_follower_risk(user: dict) -> Tuple[int, List[str]]:
    """Evaluate an individual follower and return (risk_score_0_to_100, reasons)."""
    score = 0
    reasons = []

    # Verified users are trusted
    if user.get("is_verified"):
        return 0, []

    username = (user.get("username") or "").strip().lower()
    full_name = (user.get("full_name") or "").strip().lower()

    # 1. Avatar Checks (moderate signal: missing avatar alone is not proof)
    has_anon_pic = user.get("has_anonymous_profile_picture")
    pic_url = str(user.get("profile_pic_url") or "").lower()

    if has_anon_pic is True or any(sub in pic_url for sub in DEFAULT_AVATAR_SUBSTRINGS):
        score += 25
        reasons.append("Default or missing profile picture")

    # 2. Handle / Username Digit Patterns
    digit_count = sum(c.isdigit() for c in username)
    total_chars = max(len(username), 1)
    digit_ratio = digit_count / total_chars

    trailing_match = TRAILING_DIGITS_RE.search(username)
    if trailing_match:
        num_trailing = len(trailing_match.group(1))
        if num_trailing >= 5:
            score += 25
            reasons.append(f"Heavy trailing digits ({num_trailing} numbers at end of handle)")
        elif num_trailing >= 4:
            score += 15
            reasons.append(f"Trailing digit padding ({num_trailing} numbers)")
    elif digit_ratio >= 0.40 and total_chars >= 6:
        score += 20
        reasons.append(f"High number-to-letter ratio ({int(digit_ratio * 100)}% digits)")

    # 3. Handle Entropy / Gibberish
    if total_chars >= 8:
        entropy = _calculate_entropy(username)
        vowel_count = sum(c in "aeiouy" for c in username if c.isalpha())
        alpha_count = sum(c.isalpha() for c in username)
        if alpha_count >= 6 and (vowel_count / alpha_count) < 0.15 and entropy > 3.2:
            score += 15
            reasons.append("Random consonant / gibberish handle structure")

    # 4. Spam / Commercial Keywords
    # Softened weight: single keyword in a name or handle adds +15 (does NOT flag alone < 40).
    # Heavy spam across both handle AND name or multiple spam keywords adds +30 to +40.
    matched_spam_user = [kw for kw in SPAM_KEYWORDS if kw in username]
    matched_spam_name = [kw for kw in SPAM_KEYWORDS if kw in full_name]
    matched_all = list(dict.fromkeys(matched_spam_user + matched_spam_name))
    if matched_all:
        if matched_spam_user and matched_spam_name:
            kw_score = 40
        elif len(matched_all) >= 2:
            kw_score = 30
        else:
            kw_score = 15
        score += kw_score
        reasons.append(f"Spam/promotional keyword match ({', '.join(matched_all[:2])})")

    # 5. Full name analysis
    if not full_name and (digit_count >= 3 or has_anon_pic):
        score += 10
        reasons.append("Empty display name with numeric/unverified handle")

    # 6. Repetitive / Bot Handle Tokens
    if re.search(r"^(bot_|user_\d|insta_\d|promo_|follow_)", username):
        score += 20
        reasons.append("Generic automated handle prefix")

    capped_score = min(score, 100)
    return capped_score, reasons


def audit_followers_list(followers: List[dict]) -> dict:
    """Analyze a list of followers and generate an audience authenticity audit."""
    total = len(followers)
    if total == 0:
        return {
            "total_analyzed": 0,
            "authenticity_score": 100.0,
            "fake_score": 0.0,
            "rating": "No Data (0 followers analyzed)",
            "summary": "No followers provided for audit.",
            "disclaimer": (
                "Heuristic audience authenticity indicator based on profile metadata sampling; "
                "not a definitive verdict."
            ),
            "metrics": {
                "bot_count": 0,
                "suspicious_count": 0,
                "healthy_count": 0,
                "no_avatar_count": 0,
                "digit_heavy_count": 0,
                "spam_keyword_count": 0,
                "verified_count": 0,
            },
            "flagged_accounts": [],
        }

    bot_count = 0        # score >= 70
    suspicious_count = 0 # 40 <= score < 70
    healthy_count = 0    # score < 40

    no_avatar_count = 0
    digit_heavy_count = 0
    spam_keyword_count = 0
    verified_count = 0

    flagged = []

    for f in followers:
        if f.get("is_verified"):
            verified_count += 1
            healthy_count += 1
            continue

        score, reasons = evaluate_follower_risk(f)

        has_anon = f.get("has_anonymous_profile_picture")
        pic_url = str(f.get("profile_pic_url") or "").lower()
        if has_anon is True or any(sub in pic_url for sub in DEFAULT_AVATAR_SUBSTRINGS):
            no_avatar_count += 1

        username = (f.get("username") or "").lower()
        if TRAILING_DIGITS_RE.search(username) or (
            sum(c.isdigit() for c in username) / max(len(username), 1) >= 0.4
        ):
            digit_heavy_count += 1

        if any(kw in username or kw in (f.get("full_name") or "").lower() for kw in SPAM_KEYWORDS):
            spam_keyword_count += 1

        if score >= 70:
            bot_count += 1
            flagged.append({
                "id": f.get("id"),
                "username": f.get("username"),
                "full_name": f.get("full_name"),
                "risk_score": score,
                "risk_level": "High (Likely Bot / Inactive)",
                "reasons": reasons,
            })
        elif score >= 40:
            suspicious_count += 1
            flagged.append({
                "id": f.get("id"),
                "username": f.get("username"),
                "full_name": f.get("full_name"),
                "risk_score": score,
                "risk_level": "Moderate (Suspicious Pattern)",
                "reasons": reasons,
            })
        else:
            healthy_count += 1

    # Sort flagged accounts by highest risk score first
    flagged.sort(key=lambda x: x["risk_score"], reverse=True)

    fake_ratio = (bot_count + suspicious_count * 0.5) / total
    fake_pct = round(fake_ratio * 100, 1)
    authenticity_pct = max(0.0, round(100.0 - fake_pct, 1))

    if authenticity_pct >= 85.0:
        rating = "Excellent (Organic & Healthy Audience)"
    elif authenticity_pct >= 70.0:
        rating = "Good (Normal organic noise)"
    elif authenticity_pct >= 50.0:
        rating = "Questionable (Noticeable Bot / Inactive Presence)"
    else:
        rating = "Critical (High Fake / Spam Audience Detected)"

    summary = (
        f"Analyzed {total} followers: {authenticity_pct}% authenticity score (indicator). "
        f"Detected {bot_count} probable bots ({round((bot_count/total)*100, 1)}%) "
        f"and {suspicious_count} suspicious accounts ({round((suspicious_count/total)*100, 1)}%)."
    )

    return {
        "total_analyzed": total,
        "authenticity_score": authenticity_pct,
        "fake_score": fake_pct,
        "rating": rating,
        "summary": summary,
        "disclaimer": (
            "Heuristic audience authenticity indicator based on profile metadata sampling; "
            "not a definitive verdict."
        ),
        "metrics": {
            "bot_count": bot_count,
            "suspicious_count": suspicious_count,
            "healthy_count": healthy_count,
            "no_avatar_count": no_avatar_count,
            "digit_heavy_count": digit_heavy_count,
            "spam_keyword_count": spam_keyword_count,
            "verified_count": verified_count,
        },
        "flagged_accounts": flagged,
    }
