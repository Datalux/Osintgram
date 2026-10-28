import pytest
from fastapi.testclient import TestClient

import src.web.app as appmod
from src.sentiment_analyzer import (
    score_single_comment,
    analyze_comments_sentiment,
)
from src.topic_extractor import (
    clean_tokens,
    extract_ngrams,
    extract_topics_and_cloud,
)


@pytest.fixture
def api_client():
    return TestClient(appmod.app, base_url="http://127.0.0.1:8000")


def test_score_single_comment_positive():
    res = score_single_comment("This is an amazing and beautiful photo! Love it ❤️🔥")
    assert res["sentiment"] > 0.6
    assert res["toxicity"] < 10.0
    assert res["is_spam"] is False


def test_score_single_comment_toxic_and_caps():
    res = score_single_comment("YOU ARE A PATHETIC IDIOT SCAMMER DIE 🤮🖕!!!")
    assert res["sentiment"] < -0.7
    assert res["toxicity"] >= 50.0
    assert any("Abusive" in r for r in res["reasons"]) or any("Hostile" in r for r in res["reasons"])
    assert any("CAPS" in r for r in res["reasons"])


def test_score_single_comment_spam():
    res = score_single_comment("Earn $5000 daily with crypto investment dm me on whatsapp")
    assert res["is_spam"] is True
    assert res["toxicity"] >= 20.0
    assert any("spam" in r.lower() for r in res["reasons"])


def test_score_empty_comment():
    res = score_single_comment("")
    assert res["sentiment"] == 0.0
    assert res["toxicity"] == 0.0


def test_analyze_comments_sentiment_empty():
    res = analyze_comments_sentiment([])
    assert res["total_analyzed"] == 0
    assert res["sentiment_label"] == "Neutral"
    assert res["brigading_alert"] is False


def test_analyze_comments_sentiment_positive_majority():
    comments = [
        {"text": "Amazing picture! Love this so much ❤️", "username": "fan1"},
        {"text": "Super photo, congratulations! 👏", "username": "fan2"},
        {"text": "Brilliant shot, pure fire 🔥", "username": "fan3"},
        {"text": "Great view", "username": "fan4"},
        {"text": "Ok nice", "username": "fan5"},
    ]
    res = analyze_comments_sentiment(comments)
    assert res["total_analyzed"] == 5
    assert res["sentiment_label"] == "Positive"
    assert res["overall_sentiment_score"] > 0.3
    assert res["toxicity_rating"] == "Clean"
    assert res["brigading_alert"] is False
    assert len(res["top_positive_comments"]) > 0


def test_analyze_comments_sentiment_brigading_raid():
    comments = [
        {"text": "Horrible garbage fake person 🤮", "username": "hater1"},
        {"text": "Trash content, unsubscribe now", "username": "hater2"},
        {"text": "STUPID IDIOT LIAR SCAMMER 🖕", "username": "hater3"},
        {"text": "Disgusting clown 🤡", "username": "hater4"},
        {"text": "Nice pic", "username": "fan1"},
    ]
    res = analyze_comments_sentiment(comments)
    assert res["total_analyzed"] == 5
    assert res["brigading_alert"] is True
    assert "hostility" in (res["brigading_details"] or "").lower()
    assert len(res["top_toxic_comments"]) >= 3


def test_topic_extractor_tokens_and_ngrams():
    text = "Exploring the beautiful city of Milan and visiting the Duomo cathedral with @friend https://example.com #milan #travel"
    tokens = clean_tokens(text)
    assert "milan" in tokens
    assert "duomo" in tokens
    assert "cathedral" in tokens
    # Stopwords like 'the', 'of', 'and', 'with' removed
    assert "the" not in tokens
    assert "with" not in tokens
    # Mentions and links removed
    assert "@friend" not in tokens
    assert "https" not in tokens

    bigrams = extract_ngrams(tokens, 2)
    assert len(bigrams) >= 1
    trigrams = extract_ngrams(tokens, 3)
    assert len(trigrams) >= 1


def test_extract_topics_and_cloud():
    texts = [
        "Summer vacation in Venice exploring canals #venice #travel",
        "Best summer trip in Venice Italy #venice #italy",
        "Coffee in Venice morning sunshine #venice #coffee",
    ]
    res = extract_topics_and_cloud(texts)
    assert res["total_texts"] == 3
    assert res["total_words_extracted"] > 0

    cloud = res["word_cloud"]
    words = [item["text"] for item in cloud]
    assert "venice" in words
    assert "summer" in words
    # Venice has highest frequency
    venice_item = next(item for item in cloud if item["text"] == "venice")
    assert venice_item["count"] == 6
    assert venice_item["weight"] == 100

    hashtags = [h["hashtag"] for h in res["hashtags"]]
    assert "#venice" in hashtags


def test_service_sentiment_and_topics_mock(monkeypatch):
    from src.osint_service import OsintgramService

    class FakeApi:
        def user_by_username_v2(self, username):
            return {"user": {"pk": 555, "username": username, "is_private": False}}

    service = OsintgramService("target_test", FakeApi())
    monkeypatch.setattr(service, "get_comment_data", lambda limit_posts=10: [
        {"comment": "Amazing post, love your work! ❤️", "username": "alice"},
        {"comment": "Awesome content", "username": "bob"},
    ])
    monkeypatch.setattr(service, "get_captions", lambda limit_posts=15: [
        "Enjoying nature and mountains #nature #hiking",
        "Mountain hike today #hiking",
    ])

    sent_res = service.analyze_sentiment(limit_posts=2)
    assert sent_res["total_analyzed"] == 2
    assert sent_res["overall_sentiment_score"] > 0.3

    topic_res = service.extract_topics(source="all", limit_posts=2)
    assert topic_res["total_texts"] == 4  # 2 captions + 2 comments
    cloud_words = [item["text"] for item in topic_res["word_cloud"]]
    assert "mountain" in cloud_words or "mountains" in cloud_words


def test_nlp_api_endpoints(api_client, monkeypatch):
    class FakeService:
        def analyze_sentiment(self, limit_posts=10):
            return {
                "total_analyzed": 10,
                "overall_sentiment_score": 0.5,
                "sentiment_label": "Positive",
                "average_toxicity_score": 5.0,
                "toxicity_rating": "Clean",
                "distribution": {"positive": 8, "neutral": 2, "negative": 0},
                "brigading_alert": False,
            }

        def extract_topics(self, source="all", limit_posts=15):
            return {
                "total_texts": 15,
                "word_cloud": [{"text": "paris", "count": 10, "weight": 100}],
                "top_bigrams": [{"phrase": "eiffel tower", "count": 5}],
                "hashtags": [{"hashtag": "#paris", "count": 8}],
            }

    monkeypatch.setattr(appmod, "build_service", lambda target: FakeService())
    headers = {"origin": "http://127.0.0.1:8000"}

    # Sentiment endpoint
    resp1 = api_client.post("/api/target/test_user/nlp/sentiment", json={"limit_posts": 5}, headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["ok"] is True
    assert resp1.json()["sentiment"]["sentiment_label"] == "Positive"

    # Topics endpoint
    resp2 = api_client.post("/api/target/test_user/nlp/topics", json={"source": "all", "limit_posts": 10}, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["ok"] is True
    assert resp2.json()["topics"]["total_texts"] == 15
