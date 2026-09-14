"""Bundle Instagram media into a zip the browser can save.

The web UI only ever shows links to Instagram's CDN; saving a whole set (a
photo gallery, a carousel, the stories currently up) meant clicking them one
by one. This fetches them server-side and packs them into one archive.

The URL list comes from the page, so it is treated as untrusted input: only
Instagram's own CDN hosts are fetched (otherwise this endpoint would be an
open proxy for any address the browser could name - including a local
network one), and the size/count are capped.
"""
import io
import posixpath
import re
import zipfile
from urllib.parse import unquote, urlparse

import httpx

# Instagram serves media from these (scontent-*.cdninstagram.com,
# instagram.f*.fbcdn.net, ...). Nothing else is fetched.
ALLOWED_HOSTS = (".cdninstagram.com", ".fbcdn.net")
MAX_FILES = 100
MAX_TOTAL_BYTES = 300 * 1024 * 1024
PER_FILE_TIMEOUT = 20.0


class DownloadError(Exception):
    """The request cannot be served at all (nothing usable to download)."""


def is_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == h.lstrip(".") or host.endswith(h) for h in ALLOWED_HOSTS)


def _filename(url: str, index: int, used: set) -> str:
    """A readable, unique name for the archive entry."""
    path = urlparse(url).path
    base = posixpath.basename(unquote(path)) or "media"
    base = re.sub(r"[^\w.-]+", "_", base)[:60]
    if "." not in base:
        base += ".jpg"
    name = f"{index:03d}_{base}"
    while name in used:
        index += 1
        name = f"{index:03d}_{base}"
    used.add(name)
    return name


def build_zip(urls: list) -> tuple:
    """Fetch every allowed URL and pack it. Returns (zip bytes, report).

    A file that can't be fetched doesn't fail the archive: it's listed in
    errori.txt inside it, so a partial download is still usable.
    """
    allowed = [u for u in urls if isinstance(u, str) and is_allowed(u)]
    skipped = len(urls) - len(allowed)
    if not allowed:
        raise DownloadError("No downloadable media: the URLs are not on Instagram's CDN.")
    allowed = list(dict.fromkeys(allowed))[:MAX_FILES]  # de-duplicate, then cap

    buffer = io.BytesIO()
    used: set = set()
    errors = []
    total = 0
    saved = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:  # media is already compressed
        with httpx.Client(timeout=PER_FILE_TIMEOUT, follow_redirects=True) as client:
            for index, url in enumerate(allowed, start=1):
                if total >= MAX_TOTAL_BYTES:
                    errors.append(f"{url}\n  -> saltato: superato il limite complessivo di dimensione")
                    continue
                try:
                    response = client.get(url)
                    response.raise_for_status()
                except httpx.HTTPError as e:
                    errors.append(f"{url}\n  -> {type(e).__name__}: {e}")
                    continue
                content = response.content
                total += len(content)
                saved += 1
                archive.writestr(_filename(url, index, used), content)
        if errors:
            archive.writestr("errori.txt", "\n".join(errors))
    return buffer.getvalue(), {"saved": saved, "failed": len(errors), "skipped": skipped, "bytes": total}
