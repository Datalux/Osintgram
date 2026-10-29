"""Pure-Python Investigation Dossier PDF Generator.

Zero external C-dependencies: generates standard PDF 1.4 documents using
built-in standard Type 1 fonts (Helvetica, Helvetica-Bold, Courier, Courier-Bold).
Produces standalone, print-ready investigation dossier reports.

Text is written with WinAnsiEncoding (Windows-1252), so Western European
accents are shown correctly. Standard fonts cannot draw other scripts
(Cyrillic, Arabic, CJK, emoji, ...): accents Windows-1252 lacks are reduced to
their base letter (ś -> s, ł -> l) and anything else is shown as "?".
"""
import datetime
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# Punctuation and symbols with a plain-ASCII reading.
_PUNCTUATION = {
    "—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'",
    "•": "*", "·": "*", "✓": "[x]", "✔": "[x]", "✗": "[ ]", "✘": "[ ]",
}

# Letters that do not decompose into a base letter plus an accent.
_TRANSLITERATE = {"ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ı": "i"}


def _winansi_fallback(ch: str) -> str:
    """Return `ch` if WinAnsi can show it, else its base letter, else ''."""
    try:
        ch.encode("cp1252")
        return ch
    except UnicodeEncodeError:
        pass
    ch = _TRANSLITERATE.get(ch, ch)
    base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
    try:
        base.encode("cp1252")
        return base
    except UnicodeEncodeError:
        return ""


def _clean_text(text: Any) -> str:
    """Reduce text to what WinAnsiEncoding can show (no PDF escaping)."""
    out: List[str] = []
    lost = False
    for ch in unicodedata.normalize("NFC", str(text or "")):
        rep = _PUNCTUATION.get(ch)
        category = unicodedata.category(ch)
        if rep is None:
            if category in ("Cc", "Zs", "Zl", "Zp"):
                rep = " "
            elif category in ("Cf", "Mn", "Me"):
                continue  # zero-width joiners, variation selectors, stray accents
            elif 32 <= ord(ch) <= 126:
                rep = ch
            else:
                rep = _winansi_fallback(ch)
        if rep:
            out.append(rep)
            lost = False
        elif not lost:
            out.append("?")  # one "?" per run of characters we cannot draw
            lost = True
    return "".join(out)


def _escape_pdf(text: Any) -> str:
    """Escape text for a PDF string literal (WinAnsi-safe, parentheses escaped)."""
    return _clean_text(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


# Rough Helvetica advance widths (in em), enough to wrap and truncate text
# without shipping the full font metrics.
_NARROW = set("iljtfI.,;:'!|()[] ")
_WIDE = set("mwMW@%")


def _text_width(text: str, size: float) -> float:
    width = 0.0
    for ch in text:
        if ch in _NARROW:
            width += 0.28
        elif ch in _WIDE:
            width += 0.83
        elif ch.isupper():
            width += 0.68
        else:
            width += 0.52
    return width * size


def _truncate_to_width(text: Any, max_width: float, size: float) -> str:
    """Cut `text` so it fits `max_width`, ending with '..' when shortened."""
    clean = _clean_text(text)
    if _text_width(clean, size) <= max_width:
        return clean
    while clean and _text_width(clean + "..", size) > max_width:
        clean = clean[:-1]
    return clean.rstrip() + ".."


def _wrap_text(text: Any, max_width: float, size: float, max_lines: int) -> List[str]:
    """Word-wrap `text` into at most `max_lines` lines; the last one ends in '...'."""
    words = _clean_text(text).split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _text_width(candidate, size) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        while _text_width(current, size) > max_width and len(current) > 1:
            cut = len(current) - 1
            while cut > 1 and _text_width(current[:cut], size) > max_width:
                cut -= 1
            lines.append(current[:cut])
            current = current[cut:]
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _truncate_to_width(lines[-1] + "...", max_width, size)
    return lines or [""]


def _safe_timestamp(value: Any) -> float:
    """A usable POSIX timestamp, or now when `value` is missing or out of range."""
    now = datetime.datetime.now().timestamp()
    try:
        ts = float(value)
        datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return now
    return ts if ts > 0 else now


def _dicts(value: Any) -> List[Dict[str, Any]]:
    """The dict items of a list; anything else yields an empty list."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


class PDFDocument:
    """Low-level PDF 1.4 document builder."""

    def __init__(self, page_width: float = 595.28, page_height: float = 841.89):
        self.width = page_width   # A4 width in points
        self.height = page_height  # A4 height in points
        self.objects: List[bytes] = []
        self.page_streams: List[bytes] = []

    def add_page(self, stream_bytes: bytes):
        self.page_streams.append(stream_bytes)

    def to_bytes(self) -> bytes:
        total_pages = len(self.page_streams)
        if total_pages == 0:
            self.add_page(b"")
            total_pages = 1

        objects: List[bytes] = []

        def add_obj(data: bytes) -> int:
            objects.append(data)
            return len(objects)

        # 1: Catalog
        catalog_id = add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")
        # 2: Pages (placeholder)
        pages_id = add_obj(b"")

        # Fonts: F1 (Helvetica), F2 (Helvetica-Bold), F3 (Courier), F4 (Courier-Bold)
        # WinAnsiEncoding: without it viewers fall back to StandardEncoding and
        # accented letters (e.g. é, ñ, ü) are drawn as the wrong glyph.
        def font(base: str) -> bytes:
            return (
                f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} "
                "/Encoding /WinAnsiEncoding >>"
            ).encode("ascii")

        f1_id = add_obj(font("Helvetica"))
        f2_id = add_obj(font("Helvetica-Bold"))
        f3_id = add_obj(font("Courier"))
        f4_id = add_obj(font("Courier-Bold"))

        font_res = (
            f"<< /Font << /F1 {f1_id} 0 R /F2 {f2_id} 0 R "
            f"/F3 {f3_id} 0 R /F4 {f4_id} 0 R >> >>"
        ).encode("ascii")

        page_obj_ids = []
        for stream in self.page_streams:
            content_id = add_obj(
                f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
                + stream
                + b"\nendstream"
            )
            page_id = add_obj(
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {self.width:.2f} {self.height:.2f}] "
                f"/Contents {content_id} 0 R /Resources {font_res.decode('ascii')} >>".encode("ascii")
            )
            page_obj_ids.append(page_id)

        # Finalize Pages object
        kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
        objects[pages_id - 1] = (
            f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_obj_ids)} >>".encode("ascii")
        )

        # Output compilation with cross-reference table
        out = [b"%PDF-1.4\n"]
        offsets = [0]
        for i, obj in enumerate(objects, 1):
            offsets.append(sum(len(x) for x in out))
            out.append(f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")

        start_xref = sum(len(x) for x in out)
        out.append(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        out.append(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.append(f"{off:010d} 00000 n \n".encode("ascii"))

        out.append(
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n".encode("ascii")
        )
        out.append(f"startxref\n{start_xref}\n%%EOF\n".encode("ascii"))

        return b"".join(out)


class DossierPDFCanvas:
    """High-level dossier report formatter with automatic multi-page flow."""

    MAX_VALUE_LINES = 6      # longest wrapped value (e.g. a biography), in lines
    VALUE_LINE_HEIGHT = 11.0

    def __init__(self, target: str, dossier_id: str = "", timestamp: Optional[float] = None):
        self.target = str(target or "target").lstrip("@")
        self.dossier_id = dossier_id or "RUN-1"
        self.timestamp = _safe_timestamp(timestamp)
        self.doc = PDFDocument()

        self.width = 595.28
        self.height = 841.89
        self.left = 40.0
        self.right = 555.0
        self.content_width = self.right - self.left
        self.top = 800.0
        self.bottom = 45.0

        self.current_y = self.top
        self.current_stream: List[str] = []
        self.pages_data: List[List[str]] = []

    def _start_new_page(self):
        if self.current_stream:
            self.pages_data.append(self.current_stream)
        self.current_stream = []
        self.current_y = self.top
        self._render_page_header()

    def _ensure_space(self, height: float):
        if (self.current_y - height) < self.bottom:
            self._start_new_page()

    def _render_page_header(self):
        # Top running header bar
        y = self.top + 10
        self.current_stream.append(
            f"q 0.06 0.09 0.16 rg {self.left:.2f} {y - 4:.2f} {self.content_width:.2f} 20 re f Q\n"
        )
        self.current_stream.append(
            f"BT /F2 8 Tf 1 1 1 rg {self.left + 8:.2f} {y:.2f} Td "
            f"(OSINTGRAM INVESTIGATION DOSSIER // CASE: @{_escape_pdf(self.target)}) Tj ET\n"
        )
        date_str = datetime.datetime.fromtimestamp(self.timestamp, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self.current_stream.append(
            f"BT /F1 7 Tf 0.7 0.75 0.85 rg 420.00 {y:.2f} Td "
            f"({_escape_pdf(date_str)}) Tj ET\n"
        )
        self.current_y = self.top - 20

    def draw_cover_banner(self):
        banner_h = 65.0
        self.current_y -= banner_h
        y = self.current_y

        # Navy banner background
        self.current_stream.append(
            f"q 0.06 0.09 0.16 rg {self.left:.2f} {y:.2f} {self.content_width:.2f} {banner_h:.2f} re f Q\n"
        )
        # Left accent border
        self.current_stream.append(
            f"q 0.36 0.32 0.94 rg {self.left:.2f} {y:.2f} 5.00 {banner_h:.2f} re f Q\n"
        )

        # Title
        self.current_stream.append(
            f"BT /F2 15 Tf 1 1 1 rg {self.left + 16:.2f} {y + 40:.2f} Td "
            f"(OSINTGRAM INVESTIGATION DOSSIER) Tj ET\n"
        )
        self.current_stream.append(
            f"BT /F2 8 Tf 0.55 0.5 0.95 rg {self.left + 16:.2f} {y + 26:.2f} Td "
            f"(INTELLIGENCE ASSESSMENT & TARGET RECONNAISSANCE) Tj ET\n"
        )

        # Target badge (right side)
        date_str = datetime.datetime.fromtimestamp(self.timestamp, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self.current_stream.append(
            f"BT /F2 12 Tf 1 1 1 rg 340.00 {y + 40:.2f} Td "
            f"(TARGET: @{_escape_pdf(self.target)}) Tj ET\n"
        )
        self.current_stream.append(
            f"BT /F1 8 Tf 0.7 0.75 0.85 rg 340.00 {y + 26:.2f} Td "
            f"(Case ID: {_escape_pdf(self.dossier_id)}) Tj ET\n"
        )
        self.current_stream.append(
            f"BT /F1 7 Tf 0.6 0.65 0.75 rg 340.00 {y + 14:.2f} Td "
            f"(Generated: {_escape_pdf(date_str)}) Tj ET\n"
        )
        self.current_y -= 18

    def add_section_header(self, title: str):
        self._ensure_space(34)
        self.current_y -= 22
        y = self.current_y

        # Header bar
        self.current_stream.append(
            f"q 0.95 0.96 0.98 rg {self.left:.2f} {y:.2f} {self.content_width:.2f} 18 re f Q\n"
        )
        self.current_stream.append(
            f"q 0.36 0.32 0.94 rg {self.left:.2f} {y:.2f} 3.00 18 re f Q\n"
        )
        self.current_stream.append(
            f"BT /F2 9 Tf 0.1 0.15 0.25 rg {self.left + 10:.2f} {y + 5:.2f} Td "
            f"({_escape_pdf(title.upper())}) Tj ET\n"
        )
        self.current_y -= 8

    def add_stat_tiles(self, tiles: List[Tuple[str, str]]):
        self._ensure_space(45)
        self.current_y -= 38
        y = self.current_y
        tile_w = (self.content_width - (len(tiles) - 1) * 8) / len(tiles)

        for i, (label, val) in enumerate(tiles):
            tx = self.left + i * (tile_w + 8)
            self.current_stream.append(
                f"q 0.97 0.98 0.99 rg {tx:.2f} {y:.2f} {tile_w:.2f} 36 re f Q\n"
            )
            self.current_stream.append(
                f"q 0.85 0.88 0.92 RG 1 w {tx:.2f} {y:.2f} {tile_w:.2f} 36 re S Q\n"
            )
            # Label
            self.current_stream.append(
                f"BT /F1 7 Tf 0.45 0.5 0.6 rg {tx + 8:.2f} {y + 22:.2f} Td "
                f"({_escape_pdf(label.upper())}) Tj ET\n"
            )
            # Value
            self.current_stream.append(
                f"BT /F2 11 Tf 0.1 0.15 0.25 rg {tx + 8:.2f} {y + 8:.2f} Td "
                f"({_escape_pdf(val)}) Tj ET\n"
            )
        self.current_y -= 12

    def add_key_value_rows(self, rows: List[Tuple[str, str]]):
        value_x = self.left + 150
        value_width = self.right - value_x - 4
        for k, v in rows:
            lines = _wrap_text(v, value_width, 8, self.MAX_VALUE_LINES)
            extra = self.VALUE_LINE_HEIGHT * (len(lines) - 1)
            self._ensure_space(18 + extra)
            self.current_y -= 16
            y = self.current_y
            # Key
            self.current_stream.append(
                f"BT /F2 8 Tf 0.3 0.35 0.45 rg {self.left + 4:.2f} {y + 4:.2f} Td "
                f"({_escape_pdf(k)}) Tj ET\n"
            )
            # Value, wrapped over up to MAX_VALUE_LINES lines
            for i, line in enumerate(lines):
                self.current_stream.append(
                    f"BT /F1 8 Tf 0.1 0.12 0.18 rg {value_x:.2f} "
                    f"{y + 4 - self.VALUE_LINE_HEIGHT * i:.2f} Td ({_escape_pdf(line)}) Tj ET\n"
                )
            # Zebra line under the last line of the row
            y -= extra
            self.current_stream.append(
                f"q 0.91 0.93 0.96 RG 0.5 w {self.left:.2f} {y:.2f} m {self.right:.2f} {y:.2f} l S Q\n"
            )
            self.current_y -= extra
        self.current_y -= 8

    def add_table(self, headers: List[str], rows: List[List[str]], col_widths: Optional[List[float]] = None):
        if not col_widths:
            col_widths = [self.content_width / len(headers)] * len(headers)

        # Header row
        self._ensure_space(24)
        self.current_y -= 18
        y = self.current_y

        self.current_stream.append(
            f"q 0.92 0.94 0.97 rg {self.left:.2f} {y:.2f} {self.content_width:.2f} 16 re f Q\n"
        )
        cur_x = self.left
        for h, w in zip(headers, col_widths):
            self.current_stream.append(
                f"BT /F2 7.5 Tf 0.2 0.25 0.35 rg {cur_x + 6:.2f} {y + 4:.2f} Td "
                f"({_escape_pdf(h.upper())}) Tj ET\n"
            )
            cur_x += w
        self.current_y -= 2

        # Data rows
        for idx, row in enumerate(rows):
            self._ensure_space(16)
            self.current_y -= 15
            y = self.current_y

            bg_rgb = "0.98 0.99 1.0" if (idx % 2 == 0) else "1.0 1.0 1.0"
            self.current_stream.append(
                f"q {bg_rgb} rg {self.left:.2f} {y:.2f} {self.content_width:.2f} 14 re f Q\n"
            )
            self.current_stream.append(
                f"q 0.91 0.93 0.96 RG 0.5 w {self.left:.2f} {y:.2f} m {self.right:.2f} {y:.2f} l S Q\n"
            )

            cur_x = self.left
            for cell, w in zip(row, col_widths):
                # Truncate the clean text, then escape: cutting an escaped string
                # could leave a lone backslash that swallows the closing ")".
                c_str = _escape_pdf(_truncate_to_width(cell, w - 10, 7.5))
                self.current_stream.append(
                    f"BT /F1 7.5 Tf 0.1 0.12 0.18 rg {cur_x + 6:.2f} {y + 3:.2f} Td "
                    f"({c_str}) Tj ET\n"
                )
                cur_x += w
        self.current_y -= 8

    def build_pdf(self) -> bytes:
        if self.current_stream:
            self.pages_data.append(self.current_stream)

        total_pages = len(self.pages_data) or 1
        for page_idx, stream_ops in enumerate(self.pages_data, 1):
            # Render footer on each page
            footer_ops = [
                f"q 0.85 0.88 0.92 RG 0.5 w {self.left:.2f} 32.00 m {self.right:.2f} 32.00 l S Q\n",
                f"BT /F1 7 Tf 0.5 0.55 0.65 rg {self.left:.2f} 22.00 Td "
                f"(CONFIDENTIAL // OSINT INVESTIGATION DOSSIER) Tj ET\n",
                f"BT /F1 7 Tf 0.5 0.55 0.65 rg 470.00 22.00 Td "
                f"(Page {page_idx} of {total_pages}) Tj ET\n",
            ]
            full_stream = "".join(stream_ops) + "".join(footer_ops)
            self.doc.add_page(full_stream.encode("cp1252", errors="replace"))

        return self.doc.to_bytes()


def generate_dossier_pdf(dossier_data: Dict[str, Any]) -> bytes:
    """Generate a formatted investigation dossier PDF document from scan/dossier data."""
    target = str(dossier_data.get("target") or "target")
    dossier_id = str(dossier_data.get("id") or dossier_data.get("case_id") or "RUN-1")

    pdf = DossierPDFCanvas(target=target, dossier_id=dossier_id, timestamp=dossier_data.get("saved_at"))
    pdf.draw_cover_banner()

    # Normalize cards / results (skipping anything that isn't an object)
    cards = _dicts(dossier_data.get("cards"))
    if not cards:
        cards = [{"name": r.get("name"), "result": r.get("result")} for r in _dicts(dossier_data.get("results"))]

    # 1. Target Profile
    user_info = None
    account_about = None
    for c in cards:
        if c.get("name") == "get_user_info":
            user_info = c.get("result")
        elif c.get("name") == "get_account_about":
            account_about = c.get("result")

    if user_info and isinstance(user_info, dict):
        pdf.add_section_header("1. Profile Summary & Core Metrics")
        tiles = [
            ("Followers", str(user_info.get("follower_count") or user_info.get("followers") or "0")),
            ("Following", str(user_info.get("following_count") or user_info.get("following") or "0")),
            ("Media Posts", str(user_info.get("media_count") or user_info.get("posts") or "0")),
            ("Privacy", "Private" if user_info.get("is_private") else "Public"),
        ]
        pdf.add_stat_tiles(tiles)

        meta_rows = [
            ("Username", f"@{user_info.get('username') or target}"),
            ("Full Name", user_info.get("full_name") or "-"),
            ("User ID (PK)", str(user_info.get("id") or user_info.get("pk") or "-")),
            ("Verified Account", "Yes" if user_info.get("is_verified") else "No"),
            ("Biography", user_info.get("biography") or user_info.get("bio") or "-"),
            ("External URL", user_info.get("external_url") or "-"),
        ]
        if account_about and isinstance(account_about, dict):
            if account_about.get("date_joined"):
                meta_rows.append(("Date Joined", str(account_about.get("date_joined"))))
            if account_about.get("country"):
                meta_rows.append(("Country Based", str(account_about.get("country"))))
        pdf.add_key_value_rows(meta_rows)

    # 2. Network & Connections
    followers_sample = []
    following_sample = []
    for c in cards:
        if c.get("name") == "get_followers" and isinstance(c.get("result"), list):
            followers_sample = _dicts(c.get("result"))[:15]
        elif c.get("name") == "get_followings" and isinstance(c.get("result"), list):
            following_sample = _dicts(c.get("result"))[:15]

    if followers_sample:
        pdf.add_section_header("2. Followers Sample (First 15)")
        rows = [
            [
                f"@{u.get('username', '')}",
                u.get("full_name") or "-",
                str(u.get("id") or u.get("pk") or "-"),
                "Private" if u.get("is_private") else "Public",
            ]
            for u in followers_sample
        ]
        pdf.add_table(["Handle", "Full Name", "User ID", "Status"], rows, [140.0, 175.0, 110.0, 90.0])

    if following_sample:
        pdf.add_section_header("3. Following Accounts Sample (First 15)")
        rows = [
            [
                f"@{u.get('username', '')}",
                u.get("full_name") or "-",
                str(u.get("id") or u.get("pk") or "-"),
                "Private" if u.get("is_private") else "Public",
            ]
            for u in following_sample
        ]
        pdf.add_table(["Handle", "Full Name", "User ID", "Status"], rows, [140.0, 175.0, 110.0, 90.0])

    # 3. Interactions & Comments
    commenters = []
    for c in cards:
        if c.get("name") in ("get_people_who_commented", "get_comment_data"):
            res = c.get("result")
            items = _dicts(res if isinstance(res, list) else (res.get("comments") if isinstance(res, dict) else None))
            if items:
                commenters = items[:15]
                break

    if commenters:
        pdf.add_section_header("4. Key Commenters & Interactions")
        rows = []
        for item in commenters:
            user = item.get("user") if isinstance(item.get("user"), dict) else {}
            uname = item.get("username") or user.get("username") or "-"
            cnt = str(item.get("count") or item.get("comments_count") or 1)
            text = item.get("text") or "-"
            rows.append([f"@{uname}", cnt, text])
        pdf.add_table(["User", "Count", "Sample Comment Text"], rows, [140.0, 65.0, 310.0])

    # 4. Geotags & Locations
    locations = []
    for c in cards:
        if c.get("name") == "get_addrs" and isinstance(c.get("result"), list):
            locations = _dicts(c.get("result"))[:15]

    if locations:
        pdf.add_section_header("5. Geotagged Locations & Addresses")
        rows = []
        for loc in locations:
            name = loc.get("name") or loc.get("location_name") or "-"
            addr = loc.get("address") or loc.get("city") or "-"
            lat = str(loc.get("lat") or loc.get("latitude") or "")
            lng = str(loc.get("lng") or loc.get("longitude") or "")
            coords = f"{lat[:7]}, {lng[:7]}" if lat and lng else "-"
            rows.append([name, addr, coords])
        pdf.add_table(["Location Name", "Address / City", "Coordinates"], rows, [185.0, 200.0, 130.0])

    # 5. Hashtags
    hashtags = []
    for c in cards:
        if c.get("name") == "get_hashtags" and isinstance(c.get("result"), (list, dict)):
            res = c.get("result")
            if isinstance(res, list):
                hashtags = res[:20]
            elif isinstance(res, dict):
                hashtags = list(res.items())[:20]

    if hashtags:
        pdf.add_section_header("6. Top Hashtags Used")
        tag_strings = []
        for t in hashtags:
            if isinstance(t, tuple):
                tag_strings.append(f"#{t[0]} ({t[1]})")
            elif isinstance(t, dict):
                tag_strings.append(f"#{t.get('name') or t.get('hashtag')} ({t.get('count', 1)})")
            else:
                tag_strings.append(f"#{str(t).lstrip('#')}")
        # Group into rows of 4
        rows = []
        for i in range(0, len(tag_strings), 4):
            chunk = tag_strings[i:i+4]
            while len(chunk) < 4:
                chunk.append("")
            rows.append(chunk)
        col_w = 515.0 / 4
        pdf.add_table(["Tag 1", "Tag 2", "Tag 3", "Tag 4"], rows, [col_w, col_w, col_w, col_w])

    # 6. Overall Investigation Summary
    pdf.add_section_header("7. Assessment Note")
    summary_text = [
        ("Evidence Scope", f"{len(cards)} distinct intelligence artifacts collected for @{target}."),
        ("Analysis Mode", "Headless OSINT Reconstruction"),
        ("Classification", "Investigative Working Document — Not for Public Dissemination"),
    ]
    pdf.add_key_value_rows(summary_text)

    return pdf.build_pdf()
