"""Transcript-only portal flow tests."""

import scraper


def test_fetch_transcript_returns_only_validated_pdf_without_schedule_call():
    """A live portal fetch must not depend on the removed timetable flow."""

    class FakeClient:
        def __init__(self, account, password, **_kwargs):
            assert account == "account"
            assert password == "password"
            self.closed = False

        def login(self):
            return self

        def fetch_transcript_pdf(self):
            return b"%PDF-transcript"

        def close(self):
            self.closed = True

    original_client = scraper.PortalClient
    scraper.PortalClient = FakeClient
    try:
        result = scraper._fetch_transcript_inline("account", "password")
    finally:
        scraper.PortalClient = original_client

    assert result == b"%PDF-transcript"
