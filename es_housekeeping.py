
from dataclasses import dataclass
import os
import re
import requests
import json
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from datetime import date, datetime, timezone


# Default connection settings (can be overridden by environment variables)
# ES_URL=os.environ.get("ELASTIC_URL", "http://localhost:9200").rstrip("/")

def get_es_url() -> str:
    """Liest die Basis-URL des Clusters dynamisch aus den Umgebungsvariablen."""
    return os.environ.get("ELASTIC_URL", "http://localhost:9200").rstrip("/")

es_url = get_es_url()

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
            return f"{value:.1f} {einheit}"

    return f"{value:.1f} PB"  # Falls die Größe größer als TB ist



def parse_index_age(name: str, creation_ms: str | int | None, today: date) -> int:
    """Berechnet das Alter eines Index:
    1. Priorität: Datum im Index-Namen (z.B. logs-2025.07.31) -> Retention-Datum!
    2. Priorität (Fallback): creation_date aus den Cluster-Settings.

    Diese Entscheidung ist natürlich nicht universal anwendbar.
    Sauber ist natürlich zuerst die aus settings berechnete Zeit zu berücksichteigen.
    Aber für unser trivialen Seeder gäbe es keine sinnvolle zeit, weil kreation_date hier für alle indices gleich ist.
    Daher ist die Entscheidung für den Namen als primäre Quelle für das Alter in diesem Fall sinnvoll.
    Und zusätzlich noch die idee von aus einem backup wiederhergestellten indices, die ein falsches creation_date haben könnten aber sehr warhscheinlich einen guten Namen.
    """
    # Prio 1: Suche nach YYYY.MM.DD, YYYY-MM-DD oder YYYY_MM_DD im Indexnamen
    match = re.search(r'(\d{4})[-._](\d{2})[-._](\d{2})', name)
    if match:
        try:
            year, month, day = map(int, match.groups())
            parsed_date = date(year, month, day)
            return max(0, (today - parsed_date).days)
        except ValueError:
            # Ungültiges Datum im Indexnamen, ignoriere und fahre mit Prio 2 fort
            pass

    # Prio 2: Fallback auf creation_date aus den Cluster-Settings
    if creation_ms:
        created_date = datetime.fromtimestamp(
            int(creation_ms) / 1000, tz=timezone.utc
        ).date()
        return max(0, (today - created_date).days)

    return 0  # Wenn kein Datum gefunden wurde, Alter auf 0 setzen


def get_session() -> requests.Session:
    """Erstellt eine req requesta.Session mit automatischen Retry-Logik (exponential backoff) für 5XX-Fehler auf get requests."""
    # Das ist aus meiner sicht eine Verbesserung zum elastic_api_reference der Aufgabe
    session = requests.Session()
    # retries nur für GET requests, da andere Methoden (POST, PUT, DELETE) nicht idempotent sind bzw. und daher nicht automatisch wiederholt werden sollten.
    # es ist mir ein beispiel aufgefallen wo ein retry für delete ein problem sein könnte
    retries = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session



def get_auth_and_verify():
    """Liest die Authentifizierungsinformationen (Basic Auth) und TLS-Einstellungen aus den Umgebungsvariablen """
    username = os.environ.get("ELASTIC_USER")
    password = os.environ.get("ELASTIC_PASS", "")
    auth = (username, password) if username else None

    # TLS Verification: Standard ist True (sichere Zertifikatsprüfung).
    # ELASTIC_INSECURE="true" deaktiviert die Prüfung (nur für lokale Dev-Cluster!).
    # ELASTIC_CA_BUNDLE="/pfad/zu/ca.crt" erlaubt ein eigenes CA-Zertifikat.
    ca_bundle = os.environ.get("ELASTIC_CA_BUNDLE")
    insecure = os.environ.get("ELASTIC_INSECURE", "").lower() in ("true", "1", "yes")
    verify = False if insecure else (ca_bundle if ca_bundle else True)

    return auth, verify


def get_indices(pattern: list[str] | str = "*") -> list[IndexInfo]:
    """Holt alle Indices, die dem Pattern entsprechen, und gibt sie als IndexInfo-Objekte zurück."""
    if isinstance(pattern, list):
        pattern = ",".join(pattern)

    target= pattern.replace(" ", "")
    auth, verify = get_auth_and_verify()
    session = get_session()

    # 1. Cat-API für Health, Docs-Count und Speichergröße in Bytes
    r = session.get(
        f"{es_url}/_cat/indices/{target}",
        params={
            "format": "json",
            "bytes": "b",  # Größe in Bytes
            "h": "index,health,docs.count,pri.store.size"},
        auth=auth,
        verify=verify,
        timeout=10
    )
    if r.status_code == 404 or not r.text.strip():
        return []
    r.raise_for_status()

    cat_data = r.json()
    if not cat_data:
        return []  # <-- EARLY EXIT!

    # 2. Settings-API für creation_date und ILM-Lifecycle

    s = session.get(
        f"{es_url}/{target}/_settings",
        auth=auth,
        verify=verify,
        timeout=10
    )
    s.raise_for_status()
    settings_data = s.json()

    # 3. Zusammenführen über den Index-Namen (O(1) Dictionary Lookup)
    indices: list[IndexInfo] = []
    today = date.today()

    for row in cat_data:
        name = row["index"]
        health = row.get("health", "unknown")
        doc_count = int(row.get("docs.count") or 0)
        store_size = int(row.get("pri.store.size") or 0)

        # Sichere Extraktion der Settings für genau diesen Index
        idx_settings = (
            settings_data.get(name, {}).get("settings", {}).get("index", {})
        )

        # Alter bestimmen (Prio 1: Name-Datum, Prio 2: Settings creation_date)
        age = parse_index_age(name, idx_settings.get("creation_date"), today)

        # ILM-Check: Ist eine Lifecycle-Policy aktiv?
        managed = "lifecycle" in idx_settings

        indices.append(
            IndexInfo(
                name=name,
                health=health,
                document_count=doc_count,
                primary_storage_size=store_size,
                age=age,
                managed=managed,
            )
        )

    return indices


def format_table(indices: list[IndexInfo]) -> str:
    """Formatiert eine Liste von Indices als saubere Terminal-Tabelle."""
    if not indices:
        return "Keine Indices gefunden."

    headers = ["NAME", "HEALTH", "DOCS", "SIZE", "AGE", "MANAGED"]

    health_icons = {
        "green": "🟢 green",
        "yellow": "🟡 yellow",
        "red": "🔴 red",
    }

    # Daten-Zeilen vorbereiten
    rows = []
    for idx in indices:
        h_display = health_icons.get(idx.health.lower(), idx.health)
        rows.append(
            [
                idx.name,
                h_display,
                str(idx.document_count),
                idx.human_size,
                f"{idx.age}d",
                "Yes" if idx.managed else "No",
            ]
        )

    # Maximale Breite pro Spalte berechnen
    col_widths = [len(h) for h in headers]
    for row in rows:
        for col_idx, cell in enumerate(row):
            col_widths[col_idx] = max(col_widths[col_idx], len(cell))

    # Kopfzeile und Trennlinie bauen
    header_line = "  ".join(
        h.ljust(col_widths[i]) for i, h in enumerate(headers)
    )
    separator_line = "  ".join("-" * col_widths[i] for i in range(len(headers)))

    # Zeilen zusammenbauen
    body_lines = [
        "  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row))
        for row in rows
    ]

    return "\n".join([header_line, separator_line] + body_lines)


def format_json(indices: list[IndexInfo]) -> str:
    """Formatiert eine Liste von Indices als maschinenlesbares JSON."""
    data = [
        {
            "name": idx.name,
            "health": idx.health,
            "document_count": idx.document_count,
            "primary_storage_size_bytes": idx.primary_storage_size,
            "primary_storage_size": idx.human_size,
            "age_days": idx.age,
            "managed": idx.managed,
        }
        for idx in indices
    ]
    return json.dumps(data, indent=2)


def find_stale_indices(
    indices: list[IndexInfo], older_than_days: int
) -> list[IndexInfo]:
    """Findet alle Indices, die älter als older_than_days Tage und KEINE System-Indices sind."""
    return [
        idx
        for idx in indices
        if idx.age > older_than_days and not idx.is_system_index
    ]


def delete_indices(indices: list[IndexInfo]) -> list[str]:
    """Löscht die angegebenen Indices endgültig aus Elasticsearch."""
    if not indices:
        return []

    # Letzte Sicherheits-Barriere: Niemals System-Indices löschen!
    names = [idx.name for idx in indices]
    for name in names:
        if name.startswith("."):
            raise ValueError(
                f"SICHERHEITSALARM: Versuch, System-Index '{name}' zu löschen, wurde blockiert!"
            )

    target = ",".join(names)
    auth, verify = get_auth_and_verify()
    # DELETE-Aufrufe bewusst ohne automatischen Retry absetzen (Schutz vor inkonsistenten Mutationen)
    r = requests.delete(f"{es_url}/{target}", auth=auth, verify=verify, timeout=30)
    r.raise_for_status()
    return names


def close_indices(indices: list[IndexInfo]) -> list[str]:
    """Schliesst die angegebenen Indices (gibt JVM-Heap frei, erhält Rohdaten auf Disk für Compliance)."""
    if not indices:
        return []

    # Letzte Sicherheits-Barriere: Niemals System-Indices schliessen!
    names = [idx.name for idx in indices]
    for name in names:
        if name.startswith("."):
            raise ValueError(
                f"SICHERHEITSALARM: Versuch, System-Index '{name}' zu schliessen, wurde blockiert!"
            )

    target = ",".join(names)
    auth, verify = get_auth_and_verify()
    # POST-Aufruf ohne automatische Retries (Schutz vor inkonsistenten Mutationen)
    r = requests.post(f"{es_url}/{target}/_close", auth=auth, verify=verify, timeout=30)
    r.raise_for_status()
    return names
