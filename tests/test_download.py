"""Tests for the media zip bundler (src/web/download.py)."""
import io
import zipfile

import httpx
import pytest

from src.web import download

CDN = "https://scontent-lga3-2.cdninstagram.com/v/t51/photo.jpg"
CDN2 = "https://instagram.fmxp5-1.fna.fbcdn.net/v/t51/clip.mp4"


@pytest.mark.parametrize("url, allowed", [
    (CDN, True),
    (CDN2, True),
    ("http://scontent.cdninstagram.com/x.jpg", False),   # plain http
    ("https://evil.com/x.jpg", False),
    ("https://cdninstagram.com.evil.com/x.jpg", False),  # look-alike host
    ("https://127.0.0.1/secret", False),                 # no local network
    ("file:///etc/passwd", False),
])
def test_only_instagram_cdn_over_https_is_fetched(url, allowed):
    assert download.is_allowed(url) is allowed


def _fake_transport(monkeypatch, handler):
    """Route every httpx request in build_zip to `handler` (no network)."""
    real_client = httpx.Client  # captured before patching, or we'd recurse

    def client(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(download.httpx, "Client", client)


def test_builds_a_zip_of_the_fetched_media(monkeypatch):
    _fake_transport(monkeypatch, lambda request: httpx.Response(200, content=b"binary-media"))
    content, report = download.build_zip([CDN, CDN2])
    assert report == {"saved": 2, "failed": 0, "skipped": 0, "bytes": 24}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        assert [n.endswith(("photo.jpg", "clip.mp4")) for n in names] == [True, True]
        assert archive.read(names[0]) == b"binary-media"


def test_non_cdn_urls_are_skipped_not_fetched(monkeypatch):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=b"x")

    _fake_transport(monkeypatch, handler)
    _, report = download.build_zip([CDN, "https://evil.com/x.jpg", "https://127.0.0.1/x"])
    assert report["saved"] == 1 and report["skipped"] == 2
    assert seen == [CDN]


def test_a_failed_file_does_not_break_the_archive(monkeypatch):
    def handler(request):
        if request.url.path.endswith("clip.mp4"):
            return httpx.Response(403)
        return httpx.Response(200, content=b"ok")

    _fake_transport(monkeypatch, handler)
    content, report = download.build_zip([CDN, CDN2])
    assert report["saved"] == 1 and report["failed"] == 1
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert "errori.txt" in archive.namelist()
        assert "clip.mp4" in archive.read("errori.txt").decode()


def test_duplicates_are_downloaded_once(monkeypatch):
    calls = []
    _fake_transport(monkeypatch, lambda request: (calls.append(1), httpx.Response(200, content=b"x"))[1])
    _, report = download.build_zip([CDN, CDN, CDN])
    assert report["saved"] == 1 and len(calls) == 1


def test_file_count_is_capped(monkeypatch):
    _fake_transport(monkeypatch, lambda request: httpx.Response(200, content=b"x"))
    urls = [f"{CDN}?i={i}" for i in range(download.MAX_FILES + 20)]
    _, report = download.build_zip(urls)
    assert report["saved"] == download.MAX_FILES


def test_nothing_downloadable_raises():
    with pytest.raises(download.DownloadError):
        download.build_zip(["https://evil.com/x.jpg"])
