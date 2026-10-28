"""Multilingual Topic & N-Gram Extractor for Osintgram.

Extracts top keywords, unigrams, bigrams, and trigrams from post captions
and comments, filtering out stopwords across multiple languages to generate
weighted topic clouds and common phrase frequency data.
"""
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

# Comprehensive multilingual stopword set
COMMON_STOPWORDS: Set[str] = {
    # English
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it",
    "its", "itself", "just", "me", "more", "most", "my", "myself", "no", "nor",
    "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "same", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while", "who",
    "whom", "why", "with", "would", "you", "your", "yours", "yourself", "yourselves",
    "will", "get", "got", "like", "one", "also", "see", "really", "much", "even",

    # Polish
    "w", "z", "i", "do", "na", "to", "nie", "się", "o", "a", "po", "ze", "za", "jak",
    "od", "jest", "co", "ale", "tak", "że", "ja", "mnie", "dla", "już", "ty", "ci",
    "jego", "jej", "ich", "nas", "was", "tym", "też", "tylko", "czy", "przez", "przy",
    "oraz", "więc", "ma", "są", "być", "był", "była", "było", "będzie", "tam", "tu",

    # Italian
    "di", "il", "che", "per", "un", "in", "del", "della", "dello",
    "dei", "degli", "delle", "non", "sono", "con", "una", "uno",
    "questo", "questa", "questi", "queste", "anche", "più", "molto",
    "nel", "nella", "nello", "nei", "negli", "nelle", "alla", "allo",
    "agli", "alle", "al", "gli", "hanno", "ha", "ho", "abbiamo",
    "dallo", "dalla", "dai", "sul", "sulla", "sui", "sugli", "sulle",

    # Spanish
    "el", "la", "de", "que", "y", "en", "un", "ser", "se", "no",
    "haber", "por", "con", "su", "para", "como", "estar", "tener",
    "le", "lo", "todo", "pero", "más", "las", "los", "del", "una",
    "unos", "unas", "han", "hemos", "sin", "sobre", "este", "esta",
    "estos", "estas", "esto", "sus", "mis", "tus", "nos", "les",
}


def clean_tokens(text: str) -> List[str]:
    """Clean raw text into normalized, alphabetic lowercase tokens."""
    if not text:
        return []
    # Strip URLs
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    # Strip @mentions
    text = re.sub(r"@[\w\.\_]+", " ", text)
    # Strip # from hashtags for word extraction (keep word)
    text = re.sub(r"#([\w]+)", r"\1", text)
    # Extract alphabetic words (length >= 3)
    words = re.findall(r"\b[^\W\d_]{3,}\b", text.lower())
    return [w for w in words if w not in COMMON_STOPWORDS]


def extract_ngrams(tokens: List[str], n: int) -> List[str]:
    """Generate n-grams (phrases of n consecutive tokens) from token list."""
    if len(tokens) < n:
        return []
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def extract_topics_and_cloud(
    texts: List[str],
    top_n_keywords: int = 35,
    top_n_phrases: int = 15,
) -> Dict[str, Any]:
    """Analyze a corpus of post captions and comments to produce weighted topic cloud data."""
    if not texts:
        return {
            "total_texts": 0,
            "total_words_extracted": 0,
            "word_cloud": [],
            "top_bigrams": [],
            "top_trigrams": [],
            "hashtags": [],
        }

    all_tokens: List[str] = []
    bigrams: List[str] = []
    trigrams: List[str] = []
    raw_hashtags: List[str] = []

    for item in texts:
        if not item or not isinstance(item, str):
            continue
        # Extract hashtags
        tags = re.findall(r"#([\w]+)", item.lower())
        raw_hashtags.extend(tags)

        tokens = clean_tokens(item)
        all_tokens.extend(tokens)
        bigrams.extend(extract_ngrams(tokens, 2))
        trigrams.extend(extract_ngrams(tokens, 3))

    token_counts = Counter(all_tokens)
    bigram_counts = Counter(bigrams)
    trigram_counts = Counter(trigrams)
    hashtag_counts = Counter(raw_hashtags)

    max_freq = max(token_counts.values()) if token_counts else 1

    # Format word cloud with normalized weights (scale 10 to 100 for font-size rendering)
    word_cloud = []
    for word, count in token_counts.most_common(top_n_keywords):
        weight = max(12, int((count / max_freq) * 100))
        word_cloud.append({
            "text": word,
            "count": count,
            "weight": weight,
        })

    top_bigrams = [
        {"phrase": phrase, "count": count}
        for phrase, count in bigram_counts.most_common(top_n_phrases)
        if count >= 2
    ]

    top_trigrams = [
        {"phrase": phrase, "count": count}
        for phrase, count in trigram_counts.most_common(top_n_phrases)
        if count >= 2
    ]

    top_hashtags = [
        {"hashtag": f"#{tag}", "count": count}
        for tag, count in hashtag_counts.most_common(top_n_phrases)
    ]

    return {
        "total_texts": len(texts),
        "total_words_extracted": len(all_tokens),
        "word_cloud": word_cloud,
        "top_bigrams": top_bigrams,
        "top_trigrams": top_trigrams,
        "hashtags": top_hashtags,
    }
