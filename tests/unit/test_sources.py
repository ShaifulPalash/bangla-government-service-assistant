"""Test source registry validation and security rules.

Rules we enforce: accept valid sources, reject unapproved and lookalike
domains, prevent duplicate IDs, and ensure source IDs match their services.
"""

# Import the required tools
import pytest
from pydantic import ValidationError

from app.ingest.sources import SourceRegistry


# Create a sample source
def make_source(**overrides):
    source = {
        "id": "ppt-001",
        "title": "Test page",
        "url": "https://www.epassport.gov.bd/page",
        "service": "passport",
        "language": "en",
        "doc_type": "html",
        "capture": "manual",
        "publisher": "Test publisher",
        "verified_date": "2026-10-14",
    }
    source.update(overrides)
    return source


# Create a sample registry
def make_registry(*sources):
    return {"allowed_domains": ["gov.bd"], "sources": list(sources)}


# Test that a valid registry loads
def test_valid_registry_loads():
    registry = SourceRegistry.model_validate(make_registry(make_source()))
    assert registry.sources[0].local_path.name == "ppt-001.html"


# Test that a non-government host is rejected
def test_rejects_non_government_host():
    data = make_registry(make_source(url="https://example.com/passport"))
    with pytest.raises(ValidationError):
        SourceRegistry.model_validate(data)


# Test that a lookalike host is rejected
def test_rejects_lookalike_host():
    data = make_registry(make_source(url="https://gov.bd.evil.com/passport"))
    with pytest.raises(ValidationError):
        SourceRegistry.model_validate(data)


# Test that duplicate IDs are rejected
def test_rejects_duplicate_ids():
    data = make_registry(make_source(), make_source())
    with pytest.raises(ValidationError):
        SourceRegistry.model_validate(data)


# Test that the ID matches the service
def test_rejects_id_that_does_not_match_service():
    data = make_registry(make_source(id="nid-001", service="passport"))
    with pytest.raises(ValidationError):
        SourceRegistry.model_validate(data)


def test_rejects_http_source_url():
    data = make_registry(make_source(url="http://www.epassport.gov.bd/page"))
    with pytest.raises(ValidationError):
        SourceRegistry.model_validate(data)


def test_rejects_malformed_allowed_domain():
    data = {
        "allowed_domains": ["gov.bd", "https://evil.com"],
        "sources": [make_source()],
    }
    with pytest.raises(ValidationError):
        SourceRegistry.model_validate(data)


def test_rejects_malformed_hostname():
    data = {
        "allowed_domains": ["gov..bd"],
        "sources": [],
    }
    with pytest.raises(ValidationError):
        SourceRegistry.model_validate(data)
