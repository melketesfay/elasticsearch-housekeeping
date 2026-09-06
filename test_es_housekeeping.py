import pytest
from datetime import date, datetime , timezone
import json
from es_housekeeping import (IndexInfo, format_bytes, parse_index_age)


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
