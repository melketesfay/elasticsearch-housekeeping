import pytest

from es_housekeeping import IndexInfo
from es_housekeeping import format_bytes

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
