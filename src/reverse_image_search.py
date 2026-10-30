"""Reverse Image Search Helper for Instagram OSINT.

Generates 1-click query URLs across major visual search engines
(Google Lens, Yandex Images, Bing Visual Search, TinEye, Baidu).

Note: Instagram CDN URLs are signed and temporary; search engines fetch them
server-side, so links may expire after several hours.
"""
import urllib.parse
from typing import Any, Dict


def build_reverse_search_urls(image_url: str) -> Dict[str, str]:
    """Build direct pivot search URLs for the given image CDN URL."""
    clean_url = (image_url or "").strip()
    if not clean_url:
        return {}

    quoted = urllib.parse.quote(clean_url, safe="")

    return {
        "google_lens": f"https://lens.google.com/uploadbyurl?url={quoted}",
        "yandex": f"https://yandex.com/images/search?rpt=imageview&url={quoted}",
        "bing": (
            "https://www.bing.com/images/search?view=detailv2"
            f"&iss=sbi&form=SBIIRP&sbisrc=UrlPaste&q=imgurl:{quoted}"
        ),
        "tineye": f"https://tineye.com/search?url={quoted}",
        "baidu": (
            "https://graph.baidu.com/details?isfromsimilarity=1"
            f"&image={quoted}"
        ),
    }


class ReverseImageSearchEngine:
    """Orchestrates reverse visual search URLs."""

    def analyze(
        self,
        image_url: str,
        context: str = "profile_pic",
    ) -> Dict[str, Any]:
        """Generate reverse search links across visual search engines."""
        urls = build_reverse_search_urls(image_url)

        return {
            "image_url": image_url,
            "context": context,
            "expiry_warning": (
                "Instagram CDN URLs are signed and expire after several hours. "
                "If search engines fail to fetch the image, download the photo and "
                "upload it manually."
            ),
            "search_engines": urls,
            "engine_labels": {
                "google_lens": "Google Lens",
                "yandex": "Yandex Images",
                "bing": "Bing Visual Search",
                "tineye": "TinEye",
                "baidu": "Baidu Visual Search",
            },
        }
