import pytest
from datetime import date, datetime , timezone
import json
import argparse
from es_housekeeping import (
    IndexInfo,
    format_bytes,
    parse_index_age,
    get_session,
    get_indices
    )


def test_format_bytes():


    assert format_bytes(0) == "0 B"
    assert format_bytes(512) == "512 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1536) == "1.50 KB"
    assert format_bytes(1048576) == "1.00 MB"
    assert format_bytes(1073741824) == "1.00 GB"
    assert format_bytes(1099511627776) == "1.00 TB"
    assert format_bytes(1024**5) == "1.00 PB"  # Test for PB


def test_index_info_properties():
    """TEstet die abgeleiteten Eigenschaften @property von IndexInfo."""
    idx_normal = IndexInfo("logs-2025-01-01", "green", 1000, 1048576, 10, True)
    assert idx_normal.human_size == "1.00 MB"
    assert idx_normal.is_system_index is False

    idx_system = IndexInfo(".kibana_1", "green", 1000, 1048576, 10, True)
    assert idx_system.is_system_index is True


def test_parse_index_age_from_name_dot_format():
    """Testet die Berechnung des Alters eines Index basierend auf dem Namen im Format YYYY.MM.DD."""
    today = date(2025, 8, 1)
    age = parse_index_age("logs-2025.07.31", None, today)
    assert age == (date(2025, 8, 1) - date(2025, 7, 31)).days  # 1 Tag alt

def test_parse_index_age_from_name_dash_format():
    """Testet die Berechnung des Alters eines Index basierend auf dem Namen im Format YYYY-MM-DD."""
    today = date(2025, 8, 1)
    age = parse_index_age("logs-2025-07-30", None, today)
    assert age == (date(2025, 8, 1) - date(2025, 7, 30)).days  # 2 Tage alt

def test_parse_index_age_from_name_underscore_format():
    """Testet die Berechnung des Alters eines Index basierend auf dem Namen im Format YYYY_MM_DD."""
    today = date(2025, 8, 1)
    age = parse_index_age("logs-2025_07_29", None, today)
    assert age == (date(2025, 8, 1) - date(2025, 7, 29)).days  # 3 Tage alt

def test_parse_index_age_fallback_creation_ms():
    """Fallback Test: Kein Datum im Namen (app-config), nutzt creation_date aus Settings."""
    today = date(2026, 9, 5)
    created_dt = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    ts_ms = int(created_dt.timestamp() * 1000)

    age = parse_index_age("app-config", ts_ms, today)
    assert age == 4 # 4 Tage alt


def test_parse_index_age_missing_all():
    """Randfall: Weder Datum im Namen noch in Settings vorhanden."""
    today = date(2026, 9, 5)
    age = parse_index_age("unknown-index", None, today)
    assert age == 0

def test_get_session_retry_configuration():
    """RESILIENZ TEST: Prüft, dass HTTP-Session mit Retries (Exponential Backoff) nur für GET konfiguriert ist."""
    session = get_session()
    adapter = session.adapters["http://"]
    assert adapter.max_retries.total == 5
    assert adapter.max_retries.backoff_factor == 0.5
    assert set(adapter.max_retries.status_forcelist) == {500, 502, 503, 504}
    assert set(adapter.max_retries.allowed_methods) == {"GET"}


def test_get_indices_404_returns_empty(monkeypatch):
    """FEHLERTOLERANZ TEST: Prüft, dass ein 404 von Elasticsearch sauber als leere Liste abgefangen wird."""
    class MockResponse:
        status_code = 404
        text = '{"error":"no such index"}'

    class MockSession:
        def get(self, *args, **kwargs):
            return MockResponse()

    monkeypatch.setattr("es_housekeeping.get_session", lambda: MockSession())
    result = get_indices("nonexistent-*")
    assert result == []

def test_get_indices_success(monkeypatch):
    """HAPPY PATH TEST: Prüft das saubere Mergen von Cat-API und Settings-API zu IndexInfo."""
    class MockCatResponse:
        status_code = 200
        text = '[{"index": "logs-2025.01.01", "health": "green", "docs.count": "100", "pri.store.size": "1048576"}]'
        def json(self):
            import json
            return json.loads(self.text)
        def raise_for_status(self):
            pass

    class MockSettingsResponse:
        status_code = 200
        def json(self):
            return {
                "logs-2025.01.01": {
                    "settings": {
                        "index": {
                            "creation_date": "1735689600000",
                            "lifecycle": {"name": "logs-policy"}
                        }
                    }
                }
            }
        def raise_for_status(self):
            pass

    class MockSession:
        def get(self, url, *args, **kwargs):
            if "_cat/indices" in url:
                return MockCatResponse()
            elif "_settings" in url:
                return MockSettingsResponse()
            raise ValueError(f"Unerwartete URL: {url}")

    monkeypatch.setattr("es_housekeeping.get_session", lambda: MockSession())

    indices = get_indices("logs-*")
    assert len(indices) == 1
    idx = indices[0]
    assert idx.name == "logs-2025.01.01"
    assert idx.health == "green"
    assert idx.document_count == 100
    assert idx.primary_storage_size == 1048576
    assert idx.human_size == "1.00 MB"  # bzw 1.0 MB je nach Formatierung
    assert idx.managed is True
