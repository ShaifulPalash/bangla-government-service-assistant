"""Tests for identifying a visitor behind a proxy."""

import pytest

from app.api.guards import visitor_id


def test_connection_address_is_used_when_the_proxy_is_not_trusted():
    assert visitor_id("1.2.3.4", "10.0.0.1", trust_proxy=False) == "10.0.0.1"


def test_forwarded_address_is_used_when_the_proxy_is_trusted():
    assert visitor_id("203.0.113.7", "10.0.0.1", trust_proxy=True) == "203.0.113.7"


def test_a_forged_first_entry_is_ignored():
    # The visitor sent "9.9.9.9"; the trusted proxy then appended the real address.
    assert visitor_id("9.9.9.9, 203.0.113.7", "10.0.0.1", trust_proxy=True) == "203.0.113.7"


def test_two_trusted_hops_pick_the_entry_before_the_last():
    header = "203.0.113.7, 198.51.100.2"
    assert visitor_id(header, "10.0.0.1", True, proxy_hops=2) == "203.0.113.7"


@pytest.mark.parametrize("header", [None, "", "not-an-ip", "1.2.3.4, banana"])
def test_missing_or_malformed_header_falls_back_to_the_connection(header):
    assert visitor_id(header, "10.0.0.1", trust_proxy=True) == "10.0.0.1"


def test_no_address_at_all():
    assert visitor_id(None, None, trust_proxy=False) == "unknown"
