"""Tests for the OSINT capability layer, all against synthetic g2 fixtures."""
import httpx
import pytest

import src.osint_service as svcmod
from src.osint_service import (
    OsintgramService,
    OsintServiceError,
    PrivateProfileError,
    TargetNotFoundError,
    normalize_payload,
)
from tests.conftest import FakeHiker, carousel, photo, user, video


def test_normalize_payload_strips_typed_prefixes_and_derives_pk():
    raw = {"1ltaken_at": 5, "user": {"id": "7", "username": "x"}, "list": [{"1fpos": 1}]}
    out = normalize_payload(raw)
    assert out["taken_at"] == 5
    assert out["user"]["pk"] == "7"  # derived from id
    assert out["list"][0]["pos"] == 1


def test_normalize_payload_is_idempotent_on_legacy_shape():
    legacy = {"pk": "1", "username": "a", "taken_at": 5, "usertags": [{"user": {"pk": "2", "username": "b"}}]}
    assert normalize_payload(legacy) == legacy


def test_target_not_found(make_service):
    with pytest.raises(TargetNotFoundError):
        make_service("ghost", users={"ghost": None})


def test_media_type_counts_carousels_and_extras(make_service):
    svc = make_service(feed=[photo(1), video(2, plays=100), video(3, plays=300, coauthor="c", paid=True), carousel(4)])
    r = svc.get_media_type()
    assert (r["photos"], r["videos"], r["carousels"], r["total"]) == (1, 2, 1, 4)
    assert r["video_plays_total"] == 400 and r["video_plays_avg"] == 200
    assert r["collaborations"] == 1 and r["paid_partnerships"] == 1


def test_media_type_previews_carry_audio_coauthors_plays(make_service):
    svc = make_service(feed=[video(2, plays=100, song="Song", coauthor="mate")])
    p = svc.get_media_type()["previews"][0]
    assert p["play_count"] == 100
    assert p["audio"] == "Song — Artist"
    assert p["coauthors"] == ["mate"]
    assert p["media_url"].endswith(".mp4")
    assert p["permalink"] == "https://www.instagram.com/reel/R2/"


def test_get_user_photos_selects_only_photos_including_carousel_children(make_service):
    # 1 photo post + carousel (1,2,1) => 3 photos total; the video post yields none.
    svc = make_service(feed=[photo(1), video(2), carousel(3, media_types=(1, 2, 1))])
    photos = svc.get_user_photos()
    assert len(photos) == 3
    assert svc.get_user_photos(limit=2) == photos[:2]


def test_photo_descriptions_reports_scanned_and_found(make_service):
    svc = make_service(feed=[photo(1, alt="a red car"), photo(2, alt=None), carousel(3, media_types=(1, 1))])
    r = svc.get_photo_descriptions()
    assert r["photos_scanned"] == 4  # 2 single photos + 2 carousel photos
    assert r["with_alt_text"] == 3   # photo(1) + the two carousel children
    assert all("description" in d for d in r["descriptions"])


def test_posting_times_buckets_and_frequency(make_service):
    day = 86400
    svc = make_service(feed=[photo(1, taken_at=1_700_000_000),
                             photo(2, taken_at=1_700_000_000 + day),
                             photo(3, taken_at=1_700_000_000 + 2 * day)])
    r = svc.get_posting_times()
    assert r["posts"] == 3
    assert sum(r["by_weekday"].values()) == 3
    assert sum(r["by_hour"].values()) == 3
    assert r["avg_days_between_posts"] == 1.0
    assert len(r["timestamps"]) == 3


def test_get_addrs_keeps_coordinates(make_service, monkeypatch):
    post = photo(1)
    post["location"] = {"lat": 45.46, "lng": 9.19, "name": "Milano"}
    svc = make_service(feed=[post])
    monkeypatch.setattr(svc, "_reverse_geocode", lambda coords: type("R", (), {"address": "Milano, Italia"})())
    addrs = svc.get_addrs()
    assert addrs[0]["lat"] == 45.46 and addrs[0]["lng"] == 9.19
    assert addrs[0]["name"] == "Milano"
    assert addrs[0]["address"] == "Milano, Italia"


def test_usertags_handles_hikerapi_in_wrapper(make_service):
    tagged = {"in": [{"user": {"id": "55", "username": "tagged_one", "full_name": "Tagged One"}}]}
    svc = make_service(feed=[photo(1, usertags=tagged)])
    people = svc.get_people_tagged_by_user()
    assert people[0]["username"] == "tagged_one" and people[0]["posts"] == 1


def test_followers_map_id_to_pk(make_service):
    svc = make_service(followers=[user(1, "alice"), user(2, "bob")])
    followers = svc.get_followers()
    assert {f["username"] for f in followers} == {"alice", "bob"}
    assert all(f["id"] for f in followers)


def test_private_profile_blocks_followers(make_service):
    svc = make_service(private=True, followers=[user(1, "alice")])
    with pytest.raises(PrivateProfileError):
        svc.get_followers()


def test_highlights_parse(make_service):
    hl = [{"id": "highlight:777", "title": "trip", "media_count": 12,
           "cover_media": {"cropped_image_version": {"url": "https://cdn.test/c.jpg"}},
           "created_at": 1_700_000_000, "latest_reel_media": 1_700_500_000}]
    svc = make_service(highlights=hl)
    out = svc.get_highlights()
    assert out[0]["id"] == "777"  # numeric id extracted from "highlight:777"
    assert out[0]["title"] == "trip" and out[0]["media_count"] == 12
    assert out[0]["thumbnail_url"] == "https://cdn.test/c.jpg"


def test_suggested_profiles_keeps_meaningful_context(make_service):
    suggested = [
        {"id": "1", "username": "mate", "full_name": "Mate", "social_context": "Followed by x"},
        {"id": "2", "username": "echo", "full_name": "Echo", "social_context": "Echo"},  # echoes full_name -> dropped
    ]
    svc = make_service(suggested=suggested)
    out = svc.get_suggested_profiles()
    assert out[0]["context"] == "Followed by x"
    assert "context" not in out[1]


def test_compare_with_shares_one_counter(make_service):
    a, b = user(10, "shared"), user(11, "onlymine")
    svc = make_service(
        target="alice",
        users={"alice": {"pk": 1}, "bob": {"pk": 2}},
        followers=[a, b],
        following=[a],
    )
    r = svc.compare_with("bob", limit=500)
    assert r["other"] == "bob" and r["scope"] == "both"
    assert {u["username"] for u in r["common_followers"]} == {"shared", "onlymine"}
    assert {u["username"] for u in r["common_followings"]} == {"shared"}
    # 2 username lookups (alice on construction, bob in compare) + 4 list pages
    assert svc.api_call_count == 6


def test_compare_with_scope_followers_only(make_service):
    a = user(10, "shared")
    svc = make_service(target="alice", users={"alice": {"pk": 1}, "bob": {"pk": 2}},
                       followers=[a], following=[a])
    r = svc.compare_with("bob", scope="followers")
    assert r["scope"] == "followers"
    assert "common_followers" in r and "common_followings" not in r
    assert "target_followings" not in r["scanned"]
    # 2 username lookups + only the 2 follower pages (followings skipped)
    assert svc.api_call_count == 4


def test_compare_with_invalid_scope(make_service):
    from src.osint_service import OsintServiceError
    svc = make_service(target="alice", users={"alice": {"pk": 1}, "bob": {"pk": 2}})
    with pytest.raises(OsintServiceError):
        svc.compare_with("bob", scope="nonsense")


def test_compare_with_rejects_private_other(make_service):
    svc = make_service(target="alice", users={"alice": {"pk": 1}, "bob": {"pk": 2, "private": True}})
    with pytest.raises(PrivateProfileError):
        svc.compare_with("bob")


def _hashtag_page(codes, cursor=None):
    """A hashtag feed: medias nested in sections/layout_content."""
    medias = [{"media": {**photo(int(c[1:]), code=c), "user": {"id": "9", "username": f"u{c[-1]}", "full_name": "U"}}}
              for c in codes]
    return {"response": {"sections": [{"layout_content": {"medias": medias}}]}, "next_page_id": cursor}


class SearchClient:
    def __init__(self, pages=None, places=None, location_medias=None):
        self.pages = pages or []
        self.places = places or {"items": []}
        self.location_medias = location_medias or [[], None]
        self.calls = []

    def hashtag_medias_top_v2(self, name, page_id=None, **k):
        self.calls.append(("top", name, page_id))
        idx = int(page_id) if page_id else 0
        return self.pages[idx] if idx < len(self.pages) else {"response": {}, "next_page_id": None}

    hashtag_medias_recent_v2 = hashtag_medias_top_v2

    def fbsearch_places_v2(self, query, **k):
        self.calls.append(("places", query))
        return self.places

    def location_medias_recent_chunk_v1(self, pk, max_id=None, **k):
        self.calls.append(("location", pk, max_id))
        return self.location_medias


def test_search_hashtag_collects_posts_and_authors():
    client = SearchClient(pages=[_hashtag_page(["C1", "C2"], cursor="1"), _hashtag_page(["C3"])])
    svc = OsintgramService(None, client)  # no target at all
    result = svc.search_hashtag("#milano", limit=3)
    assert result["hashtag"] == "#milano" and result["posts"] == 3
    assert {a["username"] for a in result["authors"]} == {"u1", "u2", "u3"}
    assert result["previews"][0]["author"] == "u1"


def test_search_hashtag_respects_the_limit_without_extra_pages():
    client = SearchClient(pages=[_hashtag_page(["C1", "C2"], cursor="1"), _hashtag_page(["C3"])])
    result = OsintgramService(None, client).search_hashtag("milano", limit=2)
    assert result["posts"] == 2
    assert len(client.calls) == 1  # the second page was never requested


def test_search_hashtag_rejects_empty_and_bad_sort():
    svc = OsintgramService(None, SearchClient())
    with pytest.raises(OsintServiceError):
        svc.search_hashtag("")
    with pytest.raises(OsintServiceError):
        svc.search_hashtag("milano", sort="sideways")


def test_search_location_resolves_the_place_and_maps_v1_medias():
    places = {"items": [
        {"location": {"pk": 42, "name": "Colosseo, Roma", "address": "Roma", "lat": 41.9, "lng": 12.5}},
        {"location": {"pk": 43, "name": "Colosseo - Roma"}},
    ]}
    # The location feed answers [medias, cursor] with the "v1 chunk" shape.
    medias = [{
        "pk": "1", "id": "1_2", "code": "CX", "media_type": 1,
        "taken_at": "2026-09-11T13:43:27Z", "taken_at_ts": 1789134207,
        "thumbnail_url": "https://cdn.test/t.jpg", "caption_text": "ciao",
        "user": {"pk": "9", "username": "turista", "full_name": "Turista"},
    }]
    svc = OsintgramService(None, SearchClient(places=places, location_medias=[medias, None]))
    result = svc.search_location("colosseo", limit=10)
    assert result["place"]["name"] == "Colosseo, Roma"
    assert result["alternatives"] == ["Colosseo - Roma"]
    assert result["authors"][0]["username"] == "turista"
    preview = result["previews"][0]
    assert preview["taken_at"] == 1789134207  # the epoch, not the ISO string
    assert preview["thumbnail_url"] == "https://cdn.test/t.jpg"
    assert preview["permalink"] == "https://www.instagram.com/p/CX/"


def test_search_location_without_matches():
    with pytest.raises(OsintServiceError):
        OsintgramService(None, SearchClient(places={"items": []})).search_location("nessun luogo")


def test_target_only_commands_refuse_to_run_without_a_target():
    svc = OsintgramService(None, SearchClient())
    for call in (svc.get_followers, svc.get_user_info, svc.get_user_propic, svc.get_people_tagged_by_user):
        with pytest.raises(OsintServiceError):
            call()


def test_normalize_keeps_the_filled_spelling_of_a_duplicated_field():
    # Some feeds carry both "1ltaken_at" (empty) and "taken_at" (real).
    assert normalize_payload({"1ltaken_at": None, "taken_at": 123})["taken_at"] == 123
    assert normalize_payload({"taken_at": 123, "1ltaken_at": None})["taken_at"] == 123


def test_cancelling_stops_spending_requests(make_service):
    """Stopping a search must stop the backend calls, not just the browser."""
    import threading

    from src.osint_service import QueryCancelledError

    svc = make_service(followers=[[user(1, "a")], [user(2, "b")], [user(3, "c")]])
    cancelled = threading.Event()
    svc.api.cancelled = cancelled
    calls_before = svc.api_call_count

    cancelled.set()
    with pytest.raises(QueryCancelledError):
        svc.get_followers()
    # Not one extra request was made after the stop.
    assert svc.api_call_count == calls_before


def test_cancellation_lets_cached_responses_through(make_service):
    """A cache hit costs nothing, so it must not be blocked by the stop flag
    (this is what keeps the stop instantaneous instead of erroring early)."""
    import threading
    import time as _time

    svc = make_service(followers=[user(1, "a")])
    svc.api.cache_store = {}
    svc.api.cache_ttl_seconds = 60
    svc.get_followers()  # warms the cache
    svc.api.cancelled = threading.Event()
    svc.api.cancelled.set()
    calls_before = svc.api_call_count
    assert [f["username"] for f in svc.get_followers()] == ["a"]  # served from cache
    assert svc.api_call_count == calls_before


def test_request_budget_returns_partial_not_error(make_service):
    svc = make_service(followers=[[user(1, "a"), user(2, "b")], [user(3, "c")]])
    svc.api.call_count = 0  # ignore the construction lookup, like the app does per-query
    svc.api.max_calls = 1  # only the first page is allowed
    followers = svc.get_followers()
    assert [f["username"] for f in followers] == ["a", "b"]  # partial, no exception


class _Flaky:
    """Backend stub that fails the first `failures` calls of `user_by_id_v2`."""

    def __init__(self, failures, error=None):
        self.failures = failures
        self.error = error
        self.attempts = 0

    def user_by_id_v2(self, **kwargs):
        self.attempts += 1
        if self.attempts <= self.failures:
            if self.error is not None:
                return self.error
            raise httpx.ConnectError("connection reset")
        return {"user": {"pk": "1", "username": "a"}}


@pytest.fixture
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(svcmod, "RETRY_BASE_DELAY_SECONDS", 0)


def test_a_dropped_connection_is_retried_instead_of_ending_the_scan(no_retry_delay):
    backend = _Flaky(failures=2)
    proxy = svcmod._CountingApiProxy(backend)
    events = []
    proxy.on_call = lambda name, total, a, k, status, err: events.append(status)

    assert proxy.user_by_id_v2(id="1")["user"]["username"] == "a"
    assert backend.attempts == 3
    # Every attempt is a real (billed) request, so all three are counted.
    assert proxy.call_count == 3
    assert events == ["retry", "retry", "ok"]


def test_a_rate_limit_body_is_retried_too(no_retry_delay):
    # HikerAPI never raises on status: a 429 arrives as an ordinary body.
    backend = _Flaky(failures=1, error={"detail": "429 Too Many Requests"})
    proxy = svcmod._CountingApiProxy(backend)
    assert proxy.user_by_id_v2(id="1")["user"]["username"] == "a"
    assert backend.attempts == 2


def test_a_permanent_error_body_is_not_retried(no_retry_delay):
    backend = _Flaky(failures=5, error={"detail": "user not found"})
    proxy = svcmod._CountingApiProxy(backend)
    assert proxy.user_by_id_v2(id="1") == {"detail": "user not found"}
    assert backend.attempts == 1  # nothing transient about it, don't pay twice


def test_retries_give_up_and_raise_after_the_last_attempt(no_retry_delay):
    backend = _Flaky(failures=99)
    proxy = svcmod._CountingApiProxy(backend)
    with pytest.raises(httpx.ConnectError):
        proxy.user_by_id_v2(id="1")
    assert backend.attempts == svcmod.RETRY_ATTEMPTS


def test_a_cancelled_search_does_not_keep_retrying(no_retry_delay):
    import threading

    backend = _Flaky(failures=99)
    proxy = svcmod._CountingApiProxy(backend)
    proxy.cancelled = threading.Event()
    proxy.cancelled.set()
    # The stop flag is checked before the first request, so none is made.
    with pytest.raises(svcmod.QueryCancelledError):
        proxy.user_by_id_v2(id="1")
    assert backend.attempts == 0


def test_an_error_body_is_never_cached(no_retry_delay):
    backend = _Flaky(failures=1, error={"detail": "500 Server Error"})
    proxy = svcmod._CountingApiProxy(backend)
    proxy.cache_store = {}
    proxy.cache_ttl_seconds = 60
    proxy.user_by_id_v2(id="1")
    assert list(proxy.cache_store.values())[0][1] == {"user": {"pk": "1", "username": "a"}}
    assert len(proxy.cache_store) == 1  # only the successful retry was stored


def test_user_info_surfaces_the_whole_public_profile(make_service):
    """Everything the profile object already paid for - links, category,
    business address, cross-platform ids - not just the dozen fields the
    first version picked."""
    svc = make_service(users={"target": {"pk": 100, "extra": {
        "biography": "bio",
        "external_url": "https://example.org",
        "bio_links": [
            {"title": "Sito", "url": "https://example.org", "lynx_url": "https://l.instagram.com/x"},
            {"title": "", "lynx_url": "https://l.instagram.com/y"},   # only the tracker
            {"title": "vuoto"},                                        # no link at all
        ],
        "pronouns": ["she", "her"],
        "category_name": "Musicista",
        "public_phone_country_code": "39",
        "public_phone_number": "0212345",
        "business_contact_method": "CALL",
        "address_street": "Via Roma 1",
        "city_name": "Milano",
        "zip": "20100",
        "latitude": 45.46,
        "longitude": 9.19,
        "fbid_v2": "1784",
        "total_clips_count": 12,
        "usertags_count": 7,
        "has_anonymous_profile_picture": False,  # internal noise, must not leak
    }}})
    info = svc.get_user_info()

    assert info["external_url"] == "https://example.org"
    assert info["pronouns"] == "she/her"
    assert info["category_name"] == "Musicista" and info["fbid_v2"] == "1784"
    assert (info["latitude"], info["longitude"], info["zip"]) == (45.46, 9.19, "20100")
    assert info["total_clips_count"] == 12 and info["usertags_count"] == 7
    # The tracker URL is the fallback, and a link with no URL is dropped.
    assert info["bio_links"] == [
        {"title": "Sito", "url": "https://example.org"},
        {"title": None, "url": "https://l.instagram.com/y"},
    ]
    assert "has_anonymous_profile_picture" not in info


def test_user_info_omits_fields_the_profile_does_not_have(make_service):
    info = make_service().get_user_info()
    assert info["username"] == "target"
    for absent in ("external_url", "bio_links", "pronouns", "latitude", "fbid_v2"):
        assert absent not in info


def test_user_info_costs_no_extra_request(make_service):
    svc = make_service()
    before = svc.api_call_count
    svc.get_user_info()
    assert svc.api_call_count == before  # reads the already-fetched profile


def test_account_about_reports_country_month_and_rename_count(make_service):
    """The real endpoint answers exactly this shape: a month-precision date and
    former_usernames as a *count* string, never the old names themselves."""
    svc = make_service(about={
        "username": "target", "is_verified": True, "country": "Italy",
        "date": "January 2020", "former_usernames": "2",
    })
    about = svc.get_account_about()
    assert about["country"] == "Italy" and about["date_joined"] == "January 2020"
    assert about["is_verified"] is True
    assert about["former_usernames_count"] == 2
    # The names are not available, so no empty list pretending they might be.
    assert "former_usernames" not in about


def test_account_about_with_no_renames(make_service):
    for payload in ({"username": "t", "former_usernames": ""}, {"username": "t"}):
        assert make_service(about=payload).get_account_about()["former_usernames_count"] == 0


def test_account_about_would_show_real_names_if_ever_returned(make_service):
    """HikerAPI documents this field as "the list of former usernames" even
    though it ships a count - handle the documented shape too."""
    svc = make_service(about={"username": "t", "former_usernames": "vecchio_nome, nome_prima"})
    about = svc.get_account_about()
    assert about["former_usernames"] == ["vecchio_nome", "nome_prima"]
    assert about["former_usernames_count"] == 2


def test_account_about_needs_a_target():
    svc = OsintgramService(None, SearchClient())
    with pytest.raises(OsintServiceError):
        svc.get_account_about()
