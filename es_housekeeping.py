
from dataclasses import dataclass
import os
import re
from datetime import date, datetime


# Default connection settings (can be overridden by environment variables)
ES_URL=os.environ.get("ELASTIC_URL", "http://localhost:9200").rstrip("/")

@dataclass(frozen=True)
class IndexInfo:
    name: str
    health: str
    document_count: int
    primary_storage_size: int
    age: int
    managed: bool

    @property
    def human_size(self) -> str:
        """Return the primary storage size in a human-readable format."""
        return format_bytes(self.primary_storage_size)

    @property
    def is_system_index(self) -> bool:
        """Check if the index is a system index (starts with a dot)."""
        return self.name.startswith(".")

def format_bytes(size_bytes: int) -> str:
    """Wandelt Bytes in lesbare Einheiten (B, KB, MB, GB, TB) um."""
    if size_bytes < 1024:
        return f"{size_bytes} B"


    value = float(size_bytes)
    for einheit in ['KB', 'MB', 'GB', 'TB', 'PB']:
        value /= 1024.0
        if value < 1024.0:
            return f"{value:.2f} {einheit}"

    return f"{value:.2f} PB"  # Falls die Größe größer als TB ist



def parse_index_age(name: str, creation_ms: str | int | None, today: date) -> int:
    """Berechnet das Alter eines Index:
    1. Priorität: Datum im Index-Namen (z.B. logs-2025.07.31) -> Retention-Datum!
    2. Priorität (Fallback): creation_date aus den Cluster-Settings.
    """
    # Prio 1: Suche nach YYYY.MM.DD, YYYY-MM-DD oder YYYY_MM_DD im Indexnamen
    match = re.search(r'(\d{4})[-._](\d{2})[-._](\d{2})', name)
    if match:
        year, month, day = map(int, match.groups())
        parsed_date = date(year, month, day)
        return max(0, (today - parsed_date).days)

    # Prio 2: Fallback auf creation_date aus den Cluster-Settings
    if creation_ms:
        created_date = date.fromtimestamp(int(creation_ms) / 1000)
        return max(0, (today - created_date).days)

    return 0  # Wenn kein Datum gefunden wurde, Alter auf 0 setzen

print(parse_index_age("logs-2025-07-31", None, date(2025, 8, 1)))  # Erwartet: 1
print(parse_index_age("logs-2025-07-31", "1690848000000", date(2025, 8, 1)))  # Erwartet: 1
