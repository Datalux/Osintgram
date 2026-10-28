import pytest
from starlette.testclient import TestClient

from src.pdf_report import _escape_pdf, generate_dossier_pdf, PDFDocument
from src.web.app import app
from src.web import dossier


@pytest.fixture
def api_client():
    return TestClient(app, base_url="http://127.0.0.1:8000")


def test_escape_pdf():
    assert _escape_pdf("Normal text") == "Normal text"
    assert _escape_pdf("Test (with) parens \\ and slashes") == "Test \\(with\\) parens \\\\ and slashes"
    assert _escape_pdf("Special — dashes and “quotes”") == 'Special - dashes and "quotes"'
    assert _escape_pdf("Check ✓ mark") == "Check [x] mark"


def test_pdf_document_low_level():
    doc = PDFDocument()
    doc.add_page(b"BT /F1 12 Tf 50 700 Td (Hello World) Tj ET\n")
    data = doc.to_bytes()

    assert data.startswith(b"%PDF-1.4\n")
    assert b"%%EOF\n" in data
    assert b"/Type /Catalog" in data
    assert b"/Type /Pages" in data
    assert b"/Type /Font" in data
    assert b"xref\n" in data
    assert b"trailer\n" in data


def test_generate_dossier_pdf():
    sample_dossier = {
        "target": "target_user",
        "id": "CASE-2026-99",
        "saved_at": 1793200000.0,
        "cards": [
            {
                "name": "get_user_info",
                "result": {
                    "username": "target_user",
                    "full_name": "Target Full Name",
                    "id": "123456789",
                    "follower_count": 15000,
                    "following_count": 350,
                    "media_count": 120,
                    "is_private": False,
                    "is_verified": True,
                    "biography": "Official investigation target account bio.",
                    "external_url": "https://example.com",
                },
            },
            {
                "name": "get_account_about",
                "result": {
                    "country": "Poland",
                    "date_joined": "March 2018",
                },
            },
            {
                "name": "get_followers",
                "result": [
                    {"username": f"follower_{i}", "full_name": f"User {i}", "id": str(1000 + i)}
                    for i in range(20)
                ],
            },
            {
                "name": "get_followings",
                "result": [
                    {"username": f"following_{i}", "full_name": f"Friend {i}", "id": str(2000 + i)}
                    for i in range(10)
                ],
            },
            {
                "name": "get_comment_data",
                "result": [
                    {"username": "commenter_1", "count": 12, "text": "Great photo!"},
                    {"username": "commenter_2", "count": 5, "text": "Awesome place"},
                ],
            },
            {
                "name": "get_addrs",
                "result": [
                    {"name": "Warsaw Old Town", "city": "Warsaw", "lat": 52.249, "lng": 21.013},
                ],
            },
            {
                "name": "get_hashtags",
                "result": [("osint", 15), ("investigation", 10), ("cyber", 8), ("security", 5)],
            },
        ],
    }

    pdf_bytes = generate_dossier_pdf(sample_dossier)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-1.4\n")
    assert pdf_bytes.endswith(b"%%EOF\n")
    assert len(pdf_bytes) > 2000

    # Content verification in stream
    assert b"target_user" in pdf_bytes
    assert b"Target Full Name" in pdf_bytes
    assert b"Warsaw Old Town" in pdf_bytes
    assert b"osint" in pdf_bytes


def test_empty_dossier_pdf():
    minimal = {"target": "ghost"}
    pdf_bytes = generate_dossier_pdf(minimal)
    assert pdf_bytes.startswith(b"%PDF-1.4\n")
    assert b"%%EOF\n" in pdf_bytes
    assert b"ghost" in pdf_bytes


def test_pdf_export_endpoint(api_client):
    payload = {
        "target": "alice",
        "cards": [
            {
                "name": "get_user_info",
                "result": {"username": "alice", "full_name": "Alice Wonderland", "follower_count": 500},
            }
        ],
    }
    resp = api_client.post("/api/export/pdf", json=payload)
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/pdf"
    assert 'attachment; filename="osintgram_report_alice.pdf"' in resp.headers.get("content-disposition", "")
    assert resp.content.startswith(b"%PDF-1.4\n")
    assert b"Alice Wonderland" in resp.content


def test_dossier_pdf_endpoint(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(dossier, "DOSSIER_DIR", tmp_path / "dossier")
    run = {
        "target": "bob",
        "cards": [
            {"name": "get_user_info", "result": {"username": "bob", "full_name": "Bob Builder"}},
        ],
    }
    saved = dossier.save(run)
    dossier_id = saved["id"]

    resp = api_client.get(f"/api/dossier/bob/{dossier_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/pdf"
    assert f'filename="dossier_bob_{dossier_id}.pdf"' in resp.headers.get("content-disposition", "")
    assert resp.content.startswith(b"%PDF-1.4\n")
    assert b"Bob Builder" in resp.content
