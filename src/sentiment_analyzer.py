"""Sentiment & Toxicity Analyzer for Osintgram.

Provides zero-dependency heuristic NLP for Instagram comments and text.
Computes sentiment (-1.0 to +1.0), toxicity percentage (0-100%),
detects hostility spikes and coordinated commentary, and flags spam.
"""
import re
from typing import Any, Dict, List, Tuple

# Multilingual sentiment lexicon (words -> valence weight between -1.0 and 1.0)
SENTIMENT_LEXICON: Dict[str, float] = {
    # English Positive
    "great": 0.8, "love": 0.9, "amazing": 0.9, "awesome": 0.9, "good": 0.6,
    "best": 0.9, "beautiful": 0.8, "perfect": 0.9, "nice": 0.6, "cool": 0.6,
    "fantastic": 0.9, "super": 0.8, "wonderful": 0.9, "happy": 0.8,
    "congrats": 0.8, "congratulations": 0.8, "fire": 0.8, "cute": 0.7,
    "legend": 0.8, "goat": 0.9, "king": 0.7, "queen": 0.7, "gorgeous": 0.9,
    "brilliant": 0.8, "lovely": 0.8, "stunning": 0.9, "masterpiece": 0.9,
    "bravo": 0.8, "thanks": 0.6, "thank": 0.6,

    # English Negative / Hostile
    "bad": -0.6, "terrible": -0.9, "awful": -0.9, "horrible": -0.9,
    "worst": -0.9, "hate": -0.9, "ugly": -0.8, "trash": -0.9,
    "garbage": -0.9, "fake": -0.8, "scam": -0.9, "scammer": -1.0,
    "fraud": -0.9, "liar": -0.9, "loser": -0.8, "stupid": -0.8,
    "idiot": -0.9, "clown": -0.7, "disgusting": -0.9, "cringe": -0.7,
    "pathetic": -0.9, "shit": -0.9, "crap": -0.7, "fuck": -1.0,
    "fucking": -0.9, "bitch": -1.0, "asshole": -1.0, "kill": -1.0,
    "boring": -0.6,

    # Polish Positive
    "świetnie": 0.9, "piekna": 0.8, "piękna": 0.8, "piękne": 0.8,
    "cudownie": 0.9, "najlepszy": 0.9, "kocham": 0.9, "gratulacje": 0.8,
    "ekstra": 0.8, "sztos": 0.9, "mega": 0.7, "klasa": 0.8,
    "pozdrawiam": 0.6, "wspaniale": 0.9, "uroczo": 0.8,

    # Polish Negative
    "beznadzieja": -0.9, "okropne": -0.9, "dno": -0.9, "żenada": -0.8,
    "oszust": -1.0, "kłamca": -0.9, "brzydkie": -0.7, "gówno": -1.0,
    "debil": -1.0, "idiota": -0.9, "wypierdalaj": -1.0, "spierdalaj": -1.0,
    "kurwa": -0.8, "chuj": -1.0,

    # Italian Positive
    "bello": 0.8, "bellissimo": 0.9, "stupendo": 0.9, "ottimo": 0.8,
    "eccellente": 0.9, "meraviglioso": 0.9, "grazie": 0.6, "perfetto": 0.9,
    "complimenti": 0.8, "grande": 0.7, "auguri": 0.7,

    # Italian Negative
    "brutto": -0.7, "orribile": -0.9, "schifo": -0.9, "terribile": -0.9,
    "cattivo": -0.7, "truffa": -0.9, "falso": -0.8, "pessimo": -0.9,

    # Spanish Positive
    "hermoso": 0.8, "hermosa": 0.8, "genial": 0.8, "excelente": 0.9,
    "felicidades": 0.8, "gracias": 0.6, "bueno": 0.6, "increible": 0.9,
    "amigo": 0.6,

    # Spanish Negative
    "feo": -0.7, "mierda": -0.9, "estupido": -0.9,
    "basura": -0.9, "pesimo": -0.9, "malo": -0.6,
}

# Emoji sentiment & hostility mapping (normalized without U+FE0F)
EMOJI_VALENCE: Dict[str, Tuple[float, float]] = {
    # emoji: (sentiment_score, toxicity_score)
    "\u2764": (1.0, 0.0),  # Red heart (normalized)
    "❤️".replace("\ufe0f", ""): (1.0, 0.0),
    "😍": (1.0, 0.0), "🔥": (0.9, 0.0), "👏": (0.8, 0.0), "🙌": (0.8, 0.0),
    "✨": (0.8, 0.0), "🥰": (1.0, 0.0), "💯": (0.9, 0.0), "👍": (0.7, 0.0),
    "🎉": (0.8, 0.0), "👑": (0.8, 0.0), "💪": (0.8, 0.0), "🤩": (0.9, 0.0),
    "💖": (1.0, 0.0), "👌": (0.7, 0.0), "🌟": (0.8, 0.0),

    "🤮": (-1.0, 0.7), "💩": (-0.8, 0.6), "🤡": (-0.8, 0.6), "🖕": (-1.0, 1.0),
    "😡": (-0.9, 0.6), "🤬": (-1.0, 0.9), "👎": (-0.8, 0.3), "🤢": (-0.9, 0.6),
    "🐍": (-0.7, 0.5), "🤦": (-0.6, 0.2), "💀": (-0.3, 0.1),
}

# Explicit toxic / insult keywords (matched strictly as whole words/phrases)
TOXIC_KEYWORDS = [
    "kill yourself", "die", "kys", "whore", "slut", "bitch", "faggot",
    "retard", "idiot", "moron", "asshole", "scum", "trash", "cunt",
    "debil", "szmata", "kurwa", "wypierdalaj", "chuj", "mierda",
    "pezzo di merda",
]

# Precompiled regex patterns ensuring whole-word boundaries
TOXIC_PATTERNS = [
    (re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE), phrase)
    for phrase in TOXIC_KEYWORDS
]

# Spam / promotional trigger patterns (tracked separately from toxicity)
SPAM_PATTERNS = [
    re.compile(
        r"\b(?:crypto|forex|invest|binary|whatsapp|telegram|dm me|"
        r"check my bio|earn \$\d+)\b",
        re.I,
    ),
    re.compile(r"\b(?:\+?\d{9,15})\b"),  # raw phone numbers
]


def score_single_comment(text: str) -> Dict[str, Any]:
    """Evaluate sentiment (-1.0 to 1.0) and toxicity (0-100) of a comment."""
    if not text or not text.strip():
        return {
            "text": "",
            "sentiment": 0.0,
            "toxicity": 0.0,
            "reasons": [],
            "is_spam": False,
        }

    clean_text = text.strip()
    words = re.findall(r"\b\w+\b", clean_text.lower())
    reasons = []

    sentiment_points = 0.0
    sentiment_count = 0
    toxicity_score = 0.0

    # 1. Word-level lexicon evaluation
    for w in words:
        if w in SENTIMENT_LEXICON:
            val = SENTIMENT_LEXICON[w]
            sentiment_points += val
            sentiment_count += 1
            if val <= -0.8:
                toxicity_score += 25.0
                reasons.append(f"Negative word '{w}'")

    # 2. Emoji evaluation (stripping variation selector U+FE0F)
    normalized_emojis = clean_text.replace("\ufe0f", "")
    for ch in normalized_emojis:
        if ch in EMOJI_VALENCE:
            e_sent, e_tox = EMOJI_VALENCE[ch]
            sentiment_points += e_sent
            sentiment_count += 1
            toxicity_score += e_tox * 30.0
            if e_tox > 0.4:
                reasons.append(f"Hostile emoji {ch}")

    # 3. Explicit toxic phrase matching with strict word boundary
    for pat, phrase in TOXIC_PATTERNS:
        if pat.search(clean_text):
            toxicity_score += 50.0
            sentiment_points -= 1.0
            sentiment_count += 1
            reasons.append(f"Abusive phrase '{phrase}'")

    # 4. Aggression heuristics: CAPS LOCK and punctuation hysteria
    letters = [c for c in clean_text if c.isalpha()]
    if len(letters) >= 6:
        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if caps_ratio > 0.65:
            toxicity_score += 15.0
            reasons.append("Aggressive capitalization (CAPS LOCK)")

    if "!!!" in clean_text or "???" in clean_text or "!?" in clean_text:
        if sentiment_points < 0:
            toxicity_score += 10.0
            reasons.append("Excessive exclamation/punctuation")

    # 5. Spam detection (tracked separately without inflating toxicity)
    is_spam = False
    for pat in SPAM_PATTERNS:
        if pat.search(clean_text):
            is_spam = True
            reasons.append("Promotional spam / scam pattern")
            break

    # Normalize final metrics
    if sentiment_count > 0:
        norm_sentiment = max(
            -1.0, min(1.0, round(sentiment_points / sentiment_count, 3))
        )
    else:
        norm_sentiment = 0.0

    final_toxicity = min(100.0, round(toxicity_score, 1))

    return {
        "text": clean_text,
        "sentiment": norm_sentiment,
        "toxicity": final_toxicity,
        "reasons": list(set(reasons)),
        "is_spam": is_spam,
    }


def analyze_comments_sentiment(
    comments: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Aggregate sentiment, toxicity, and hostility spike indicators."""
    if not comments:
        return {
            "total_analyzed": 0,
            "overall_sentiment_score": 0.0,
            "sentiment_label": "Neutral",
            "average_toxicity_score": 0.0,
            "toxicity_rating": "Clean",
            "distribution": {"positive": 0, "neutral": 0, "negative": 0},
            "hostility_spike_detected": False,
            "brigading_alert": False,
            "spike_details": None,
            "brigading_details": None,
            "disclaimer": (
                "Heuristic linguistic indicator for investigative triage; "
                "not definitive proof of intent."
            ),
            "top_toxic_comments": [],
            "top_positive_comments": [],
        }

    scored_items = []
    pos_count = 0
    neu_count = 0
    neg_count = 0
    total_sentiment = 0.0
    total_toxicity = 0.0

    for c in comments:
        txt = c.get("text") or c.get("comment") or ""
        author = (
            c.get("user", {}).get("username")
            if isinstance(c.get("user"), dict)
            else c.get("username", "")
        )
        created_at = c.get("created_at") or c.get("created_at_utc") or 0

        score_res = score_single_comment(txt)
        sent = score_res["sentiment"]
        tox = score_res["toxicity"]

        total_sentiment += sent
        total_toxicity += tox

        if sent > 0.15:
            pos_count += 1
        elif sent < -0.15:
            neg_count += 1
        else:
            neu_count += 1

        scored_items.append({
            "author": author,
            "text": txt,
            "sentiment": sent,
            "toxicity": tox,
            "reasons": score_res["reasons"],
            "is_spam": score_res["is_spam"],
            "created_at": created_at,
        })

    n = len(scored_items)
    avg_sent = round(total_sentiment / n, 3)
    avg_tox = round(total_toxicity / n, 1)

    # Classify overall label
    if avg_sent >= 0.25:
        sentiment_label = "Positive"
    elif avg_sent <= -0.25:
        sentiment_label = "Negative"
    elif neg_count > pos_count * 1.5:
        sentiment_label = "Predominantly Negative"
    else:
        sentiment_label = "Neutral"

    # Toxicity category
    if avg_tox < 10.0:
        toxicity_rating = "Clean"
    elif avg_tox < 25.0:
        toxicity_rating = "Low"
    elif avg_tox < 50.0:
        toxicity_rating = "Elevated"
    elif avg_tox < 75.0:
        toxicity_rating = "Toxic"
    else:
        toxicity_rating = "Critical / Hostile"

    # Hostility Spike & Coordination indicator
    hostility_spike = False
    spike_details = None

    # Check for repeated hostile authors or duplicate text
    hostile_authors = [
        c["author"]
        for c in scored_items
        if c["toxicity"] >= 25.0 and c["author"]
    ]
    hostile_texts = [
        c["text"].strip().lower()
        for c in scored_items
        if c["toxicity"] >= 25.0
    ]
    has_coordination = (
        len(hostile_authors) > len(set(hostile_authors))
        or len(hostile_texts) > len(set(hostile_texts))
    )

    if n >= 5 and (neg_count / n >= 0.40) and avg_tox >= 25.0:
        hostility_spike = True
        coord_note = (
            " Repeat accounts/phrases detected (coordination signal)."
            if has_coordination
            else " Diverse authors (organic controversy signal)."
        )
        pct_neg = round(neg_count / n * 100)
        spike_details = (
            f"Hostility spike indicator triggered: {pct_neg}% "
            f"negative comments with average toxicity {avg_tox}%.{coord_note}"
        )

    # Top toxic and top positive comments
    toxic_sorted = sorted(
        scored_items,
        key=lambda x: (x["toxicity"], -x["sentiment"]),
        reverse=True,
    )
    positive_sorted = sorted(
        scored_items,
        key=lambda x: (x["sentiment"], -x["toxicity"]),
        reverse=True,
    )

    top_toxic = [c for c in toxic_sorted if c["toxicity"] > 20.0][:5]
    top_positive = [c for c in positive_sorted if c["sentiment"] > 0.2][:5]

    return {
        "total_analyzed": n,
        "overall_sentiment_score": avg_sent,
        "sentiment_label": sentiment_label,
        "average_toxicity_score": avg_tox,
        "toxicity_rating": toxicity_rating,
        "distribution": {
            "positive": pos_count,
            "neutral": neu_count,
            "negative": neg_count,
            "positive_pct": round(pos_count / n * 100, 1),
            "neutral_pct": round(neu_count / n * 100, 1),
            "negative_pct": round(neg_count / n * 100, 1),
        },
        "hostility_spike_detected": hostility_spike,
        "brigading_alert": hostility_spike,
        "spike_details": spike_details,
        "brigading_details": spike_details,
        "disclaimer": (
            "Heuristic linguistic indicator for investigative triage; "
            "not definitive proof of malicious coordination."
        ),
        "top_toxic_comments": top_toxic,
        "top_positive_comments": top_positive,
    }
