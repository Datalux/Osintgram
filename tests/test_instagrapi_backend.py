"""Tests that the instagrapi backend answers the HikerAPI-shaped payloads
OsintgramService expects, so both backends run the same capabilities.

instagrapi is not installed in CI, so these drive InstagrapiClient with a
hand-built stand-in for its `Client` instead of importing it - what matters
here is the translation layer, not instagrapi itself.
"""
import types

import pytest

from src.instagrapi_backend import InstagrapiClient
from src.osint_service import OsintgramService


def _media(pk, username, caption="ciao"):
    return types.SimpleNamespace(
        id=f"{pk}_1", pk=pk, code=f"C{pk}", product_type="feed", comment_count=3, like_count=42,
        media_type=1, accessibility_caption=None, caption_text=caption,
        taken_at=None, usertags=[], location=None, resources=[],
        image_versions2=types.SimpleNamespace(candidates=[types.SimpleNamespace(url=f"https://cdn/{pk}.jpg")]),
        thumbnail_url=f"https://cdn/{pk}.jpg", video_url=None,
        user=types.SimpleNamespace(pk=pk, username=username, full_name=username.title(),
                                   is_private=False, is_verified=False),
    )


class FakeInstagrapi:
    """Only the handful of methods the search capabilities reach for."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.calls = []

    def hashtag_medias_v1_chunk(self, name, max_amount=30, tab_key="", max_id=None):
        self.calls.append(("hashtag", name, tab_key, max_id))
        page = 1 if max_id else 0
        pages = [([_media(1, "anna"), _media(2, "bruno")], "cursor1"), ([_media(3, "anna")], None)]
        return pages[page]

    def fbsearch_places(self, query):
        self.calls.append(("places", query))
        return [
            types.SimpleNamespace(pk=101, name="Colosseo", address="Roma", city="Roma", lat=41.89, lng=12.49),
            types.SimpleNamespace(pk=102, name="Colosseo Archeologico", address="", city="Roma", lat=None, lng=None),
        ]

    def location_medias_v1_chunk(self, location_pk, max_amount=30, tab_key="", max_id=None):
        self.calls.append(("location", location_pk, max_id))
        return ([_media(7, "carla")], None)

    def media_pk_from_url(self, url):
        self.calls.append(("pk_from_url", url))
        # Returned as an int here on purpose, to prove the adapter's own
        # str(...) wrapping doesn't assume instagrapi already gives a string.
        return 2110901750722920960

    def media_pk_from_code(self, code):
        self.calls.append(("pk_from_code", code))
        return 2110901750722920960


def _client(fake):
    client = InstagrapiClient.__new__(InstagrapiClient)  # no login, no session file
    client._cl = fake
    return client


def test_hashtag_search_pages_and_counts_authors():
    fake = FakeInstagrapi()
    service = OsintgramService(None, _client(fake))
    result = service.search_hashtag("#milano", sort="top", limit=3)

    assert result["hashtag"] == "#milano"
    assert result["posts"] == 3
    assert [a["username"] for a in result["authors"]] == ["anna", "bruno"]  # anna posted twice
    assert result["previews"][0]["author"] == "anna"
    assert result["previews"][0]["media_url"] == "https://cdn/1.jpg"
    assert [c[2] for c in fake.calls] == ["top", "top"]  # the "recent" tab was not touched


def test_hashtag_search_stops_at_the_limit():
    fake = FakeInstagrapi()
    service = OsintgramService(None, _client(fake))
    assert service.search_hashtag("milano", limit=2)["posts"] == 2
    assert len(fake.calls) == 1  # the second page was never requested


def test_place_search_resolves_the_place_and_lists_alternatives():
    fake = FakeInstagrapi()
    service = OsintgramService(None, _client(fake))
    result = service.search_location("colosseo", limit=10)

    assert result["place"]["name"] == "Colosseo" and result["place"]["lat"] == 41.89
    assert result["alternatives"] == ["Colosseo Archeologico"]
    assert result["posts"] == 1
    assert result["previews"][0]["author"] == "carla"
    assert ("location", 101, None) in fake.calls  # the first match's pk, not the name


def test_place_search_without_matches_is_an_error():
    from src.osint_service import OsintServiceError

    fake = FakeInstagrapi()
    fake.fbsearch_places = lambda query: []
    service = OsintgramService(None, _client(fake))
    with pytest.raises(OsintServiceError):
        service.search_location("posto inesistente")


def test_hashtag_search_falls_back_when_the_chunked_method_is_missing():
    """Older instagrapi releases have no *_v1_chunk: one page, no cursor."""
    class Older:
        def hashtag_medias_top_v1(self, name, amount=30):
            return [_media(1, "anna")]

    service = OsintgramService(None, _client(Older()))
    assert service.search_hashtag("milano")["posts"] == 1


def test_media_pk_from_url_is_a_free_local_decode_on_instagrapi():
    fake = FakeInstagrapi()
    client = _client(fake)
    pk = client.media_pk_from_url_v1("https://www.instagram.com/p/B1LbfVPlwIA/")
    assert pk == "2110901750722920960"
    assert isinstance(pk, str)
    assert fake.calls == [("pk_from_url", "https://www.instagram.com/p/B1LbfVPlwIA/")]


def test_media_pk_from_code_is_a_free_local_decode_on_instagrapi():
    fake = FakeInstagrapi()
    client = _client(fake)
    pk = client.media_pk_from_code_v1("B1LbfVPlwIA")
    assert pk == "2110901750722920960" and isinstance(pk, str)
    assert fake.calls == [("pk_from_code", "B1LbfVPlwIA")]


def test_get_post_comments_works_end_to_end_on_the_instagrapi_backend():
    """Exercises the real call path: OsintgramService -> InstagrapiClient ->
    the (faked) instagrapi Client, decoding a shortcode then paging comments -
    not just the adapter's two new methods in isolation."""
    # Duck-typed the way InstagrapiClient._comment_to_dict reads a comment:
    # user_id comes from comment.user.pk, not a user_id field on the comment.
    comment = types.SimpleNamespace(
        user=types.SimpleNamespace(pk="9", username="anna", full_name="Anna"), text="nice shot")

    class Fake(FakeInstagrapi):
        def media_comments_chunk(self, media_id, max_amount, min_id=None):
            self.calls.append(("comments", media_id, min_id))
            return ([comment], None)

    fake = Fake()
    service = OsintgramService(None, _client(fake))
    result = service.get_post_comments("B1LbfVPlwIA")
    assert result == [{"post_id": "2110901750722920960", "user_id": "9", "username": "anna", "comment": "nice shot"}]
    assert not any(call[0].startswith("pk_from") for call in fake.calls)  # decoded locally
    # The bare pk (no owner suffix) is what reaches media_comments_chunk -
    # instagrapi's own media_id() upgrades it internally if it needs to.
    assert ("comments", "2110901750722920960", None) in fake.calls
