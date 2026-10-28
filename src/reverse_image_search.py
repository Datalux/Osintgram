"""Reverse Image Search & Face Pivot Helper for Instagram OSINT.

Generates 1-click pivot queries across major visual search and facial
recognition engines (Google Lens, Yandex, Bing Visual Search, TinEye, Baidu)
and computes perceptual difference hashes (dHash) for cross-platform avatar
tracking and duplicate media detection.
"""
import io
import urllib.parse
from typing import Any, Dict, Optional

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def build_reverse_search_urls(image_url: str) -> Dict[str, str]:
    """Build direct pivot search URLs for the given image CDN URL."""
    clean_url = (image_url or "").strip()
    if not clean_url:
        return {}

    quoted = urllib.parse.quote(clean_url, safe="")

    return {
        "google_lens": f"https://lens.google.com/uploadbyurl?url={quoted}",
        "yandex": (
            f"https://yandex.com/images/search?rpt=imageview&url={quoted}"
        ),
        "bing": (
            "https://www.bing.com/images/search?view=detailv2"
            f"&iss=sbi&form=SBIIRP&sbisrc=UrlPaste&q=imgurl:{quoted}"
        ),
        "tineye": f"https://tineye.com/search?url={quoted}",
        "baidu": (
            "https://graph.baidu.com/details?isfromsimilarity=1"
            f"&image={quoted}"
        ),
        "facecheck": "https://facecheck.id/",
        "pimeyes": "https://pimeyes.com/",
    }


def compute_dhash(image_bytes: bytes, hash_size: int = 8) -> Optional[str]:
    """Compute a 64-bit difference hash (dHash) from image bytes."""
    if not Image or not image_bytes:
        return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Convert to grayscale and resize to (hash_size + 1, hash_size)
            resized = img.convert("L").resize(
                (hash_size + 1, hash_size), Image.Resampling.LANCZOS
            )
            pixels = list(resized.tobytes())

            # Compare adjacent pixels in each row
            difference = []
            width = hash_size + 1
            for row in range(hash_size):
                row_offset = row * width
                for col in range(hash_size):
                    left = pixels[row_offset + col]
                    right = pixels[row_offset + col + 1]
                    difference.append(left > right)

            # Convert boolean array to hex string
            decimal_value = 0
            for idx, bit in enumerate(difference):
                if bit:
                    decimal_value += 1 << idx
            return f"{decimal_value:016x}"
    except Exception:
        return None


def hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two hex perceptual hashes."""
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return -1
    try:
        val1 = int(hash1, 16)
        val2 = int(hash2, 16)
        xor_val = val1 ^ val2
        return bin(xor_val).count("1")
    except ValueError:
        return -1


class ReverseImageSearchEngine:
    """Orchestrates reverse visual search URLs and perceptual hashes."""

    def analyze(
        self,
        image_url: str,
        image_bytes: Optional[bytes] = None,
        context: Optional[str] = "profile_pic",
    ) -> Dict[str, Any]:
        """Generate reverse search links and perceptual fingerprint."""
        urls = build_reverse_search_urls(image_url)
        dhash = compute_dhash(image_bytes) if image_bytes else None

        return {
            "image_url": image_url,
            "context": context,
            "dhash": dhash,
            "search_engines": urls,
            "engine_labels": {
                "google_lens": "Google Lens (General & Product Match)",
                "yandex": "Yandex Images (High Accuracy Face/Person Pivot)",
                "bing": "Bing Visual Search (Similar Web Images)",
                "tineye": "TinEye (Historical Crawled Web Duplicates)",
                "baidu": "Baidu Visual Search (Asian Regional Ecosystem)",
                "facecheck": "FaceCheck.id (Facial Recognition Database)",
                "pimeyes": "PimEyes (Public Face Index Search)",
            },
        }
