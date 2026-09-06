
from dataclasses import dataclass
import os

# Default connection settings (can be overridden by environment variables)
ES_URL = os.environ.get("ELASTIC_URL", "http://localhost:9200").rstrip("/")

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

    @property
    def is_empty(self) -> bool:
        """Return whether this index contains no documents."""
        return self.document_count == 0

    @classmethod
    def from_mapping(cls, data: dict) -> "IndexInfo":
        """Build an instance from an Elasticsearch index response."""
        return cls(
            name=str(data["name"]),
            health=str(data.get("health", "unknown")),
            document_count=int(data.get("document_count", data.get("docs.count", 0))),
            primary_storage_size=int(
                data.get("primary_storage_size", data.get("pri.store.size", 0))
            ),
            age=int(data.get("age", 0)),
            managed=bool(data.get("managed", False)),
        )

def format_bytes(size_bytes: int) -> str:
    """Convert a byte count to a readable binary unit."""
    if size_bytes < 0:
        raise ValueError("size_bytes must not be negative")

    if size_bytes < 1024:
        return f"{size_bytes} B"

    value = float(size_bytes)
    for unit in ("KB", "MB", "GB", "TB", "PB"):
        value /= 1024.0
        if value < 1024.0:
            return f"{value:.2f} {unit}"

    return f"{value:.2f} PB"

# Gute Completion-Vorschläge in VS Code benötigen gültiges Python, Typannotationen,
# Docstrings sowie einen ausgewählten Python-Interpreter und aktivierten Linter.

