import httpx
from scripts.fetch_sources import (
    download_source,
    is_approved_https_url,
)

ALLOWED_DOMAINS = ["ecs.gov.bd", "epassport.gov.bd"]


def test_approved_https_domain_is_accepted():
    assert is_approved_https_url("https://ecs.gov.bd/form.pdf", ALLOWED_DOMAINS)


def test_approved_subdomain_is_accepted():
    assert is_approved_https_url("https://www.ecs.gov.bd/form.pdf", ALLOWED_DOMAINS)


def test_lookalike_domain_is_rejected():
    assert not is_approved_https_url(
        "https://ecs.gov.bd.attacker.example/form.pdf", ALLOWED_DOMAINS
    )


def test_http_url_is_rejected():
    assert not is_approved_https_url("http://ecs.gov.bd/form.pdf", ALLOWED_DOMAINS)


def test_unapproved_port_is_rejected():
    assert not is_approved_https_url("https://ecs.gov.bd:8443/form.pdf", ALLOWED_DOMAINS)


def test_credentials_in_url_are_rejected():
    assert not is_approved_https_url("https://user:password@ecs.gov.bd/form.pdf", ALLOWED_DOMAINS)


def test_external_redirect_is_rejected(tmp_path, monkeypatch):
    import scripts.fetch_sources as fetcher

    monkeypatch.setattr(fetcher, "allowed_by_robots", lambda *_: True)

    def handler(request):
        return httpx.Response(
            302,
            headers={"Location": "https://attacker.example/payload.pdf"},
        )

    target = tmp_path / "form.pdf"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        success, detail = download_source(
            client,
            "https://ecs.gov.bd/form.pdf",
            target,
            "pdf",
            ALLOWED_DOMAINS,
        )

    assert not success
    assert "not an approved HTTPS destination" in detail
    assert not target.exists()


def test_invalid_pdf_is_not_saved(tmp_path, monkeypatch):
    import scripts.fetch_sources as fetcher

    monkeypatch.setattr(fetcher, "allowed_by_robots", lambda *_: True)

    def handler(request):
        return httpx.Response(200, content=b"<html>Not a PDF</html>")

    target = tmp_path / "form.pdf"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        success, detail = download_source(
            client,
            "https://ecs.gov.bd/form.pdf",
            target,
            "pdf",
            ALLOWED_DOMAINS,
        )

    assert not success
    assert "failed validation" in detail
    assert not target.exists()


def test_existing_file_is_never_overwritten(tmp_path, monkeypatch):
    import scripts.fetch_sources as fetcher

    monkeypatch.setattr(fetcher, "allowed_by_robots", lambda *_: True)

    target = tmp_path / "form.pdf"
    target.write_bytes(b"original file")

    def handler(request):
        return httpx.Response(200, content=b"%PDF-1.7\nnew content")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        success, detail = download_source(
            client,
            "https://ecs.gov.bd/form.pdf",
            target,
            "pdf",
            ALLOWED_DOMAINS,
        )

    assert not success
    assert "not overwritten" in detail
    assert target.read_bytes() == b"original file"
