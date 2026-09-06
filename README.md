# `es-housekeeping`: Production-Grade Elasticsearch Lifecycle CLI

A resilient, secure, and fail-safe command-line tool for Elasticsearch index discovery, metadata reporting, and defensive lifecycle housekeeping.

Built with **Python 3.12+ / 3.14**, standard library `argparse`, `requests`, and tested 100% offline with `pytest`.

---

## 1. Conception & Mental Model Evolution

Before writing any code, roughly two hours were invested into API research, Elasticsearch 9.4 specifics, and threat modeling. The design evolved in two distinct phases:

|                                                   Phase 1: First Sketch (Exploration & Threat Modeling)                                                    |                                                            Phase 2: Second Sketch (Focused Architecture)                                                             |
| :--------------------------------------------------------------------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------------------------------------------------------------------------------: |
|                                        <img src="docs/solution/first_sketch.png" width="400" alt="First Sketch" />                                         |                                            <img src="docs/solution/second_sketch.png" width="400" alt="Second Sketch" />                                             |
| **Exploration:** Mapping all operational facets (daemons, storage watermarks, alerting, snapshot verification). Realization: High risk of overengineering. | **Focus:** Radical reduction to the core mission: _Minimal Complexity, Maximal Clarity_. Strict sequential pipeline, fail-safe defaults, isolated security barriers. |

---

## 2. System Architecture & Workflow

```text
                  ┌───────────────────────────────┐
                  │          USER / CLI           │
                  │ python es_housekeeping.py ... │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │         LOAD CONFIG           │
                  │   .env / ELASTIC_URL / Auth   │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │    FETCH DATA (Elasticsearch) │
                  │  1. GET /_cat/indices?bytes=b │
                  │     (with Retry on 5xx)       │
                  │  2. GET /_settings            │
                  │     (with Retry on 5xx)       │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │       MERGE & NORMALIZE       │
                  │  • O(1) Dict Lookup per Name  │
                  │  • parse_index_age (Regex)    │
                  │  • Output: list[IndexInfo]    │
                  └──────────────┬────────────────┘
                                 │
            ┌────────────────────┴────────────────────┐
            │ [report]                                │ [cleanup]
            ▼                                         ▼
   ┌─────────────────┐                       ┌─────────────────┐
   │    FORMAT ?     │                       │  FILTER STALE   │
   └─┬─────────────┬─┘                       │   • age > N     │
     │ --json      │ default                 │   • name != .*  │
     ▼             ▼                         └────────┬────────┘
┌─────────┐   ┌─────────┐                             │
│  JSON   │   │  TABLE  │                             ▼
│ Output  │   │ 🟢🟡🔴  │                    ┌─────────────────┐
└─────────┘   └─────────┘                    │    --apply ?    │
                                             └─┬─────────────┬─┘
                                               │ No          │ Yes
                                               ▼             ▼
                                         ┌───────────┐ ┌───────────┐
                                         │  DRY-RUN  │ │  CONFIRM  │
                                         │  Preview  │ │   [y/N] ? │
                                         └───────────┘ └─┬───────┬─┘
                                                       │ No    │ Yes
                                                       ▼       ▼
                                                  ┌─────────┐ ┌─────────────────┐
                                                  │ Aborted │ │   --action ?    │
                                                  │(0 Delete│ └─┬─────────────┬─┘
                                                  └─────────┘   │ close (def) │ delete
                                                                ▼             ▼
                                                          ┌───────────┐ ┌───────────┐
                                                          │   CLOSE   │ │  DELETE   │
                                                          │ Heap frei │ │Hard Purge │
                                                          └───────────┘ └───────────┘
```

---

## 3. Safety Model & Security by Design

Housekeeping tools perform inherently destructive actions (`DELETE`, `_close`). This tool was engineered with multiple defensive barriers:

1. **Fail-Safe Defaults:**
   - `--dry-run` is the immutable default. Destructive execution strictly requires the `--apply` flag.
   - If index age cannot be determined, it defaults to `0d` (never stale, fail-closed).
2. **Blast Radius Reduction (No Server-Side Wildcard Deletions):**
   - `--pattern` is evaluated strictly client-side. The tool never sends wildcard queries to destructive endpoints.
   - Instead, it resolves matching indices and sends an explicit comma-separated list of verified index names (`DELETE /logs-2025.01.01,logs-2025.01.02`).
3. **Defense in Depth for System Indices (`.*`):**
   - **Barrier 1 (Policy):** `find_stale_indices()` categorially filters out system indices (`.kibana`, `.security`, etc.).
   - **Barrier 2 (Hard Assertion):** `delete_indices()` and `close_indices()` individually verify every target. If any index starts with `.`, execution is immediately aborted with a `ValueError("SICHERHEITSALARM")` before any network packet is dispatched.
4. **Zero-Leak Secret Protection:**
   - Credentials from `ELASTIC_PASS` are passed via HTTP Basic Auth headers, never logged, and never formatted into error tracebacks.
5. **Strict Stream Separation:**
   - `stdout`: Pure payload data (formatted table or clean JSON).
   - `stderr`: Status messages, confirmation prompts, dry-run notes, and errors (enabling clean UNIX piping like `es-housekeeping report --json | jq .`).

---

## 4. Installation & Environment Setup

### 4.1 Why `uv`?

We consciously selected [`uv`](https://github.com/astral-sh/uv) (developed in Rust by Astral) as our primary toolchain manager for several engineering reasons:

- **Performance:** Dependency resolution and installation is 10–100× faster than traditional `pip` or `poetry`.
- **Determinism:** The `uv.lock` file guarantees that every developer and CI runner installs byte-for-byte identical dependency versions across macOS, Linux, and Windows.
- **Automated Python Runtime Management:** `uv` automatically downloads, installs, and isolates the exact required Python version (`3.14` via `.python-version`), eliminating "wrong Python version installed on host" issues.
- **Standards Compliant & Fallback-Ready:** Built natively on modern packaging standards (PEP 517, PEP 621, PEP 735). For legacy environments, it seamlessly exports to standard `requirements.txt`.

### 4.2 Installing `uv` (macOS, Linux, Windows)

Install `uv` via the official standalone installers:

- **macOS & Linux:**

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Or via Homebrew on macOS:
  # brew install uv
  ```

- **Windows (PowerShell):**

  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  # Or via winget:
  # winget install --id=astral-sh.uv
  ```

- **Universal Fallback (via standard pip):**
  ```bash
  pip install uv
  ```

---

### 4.3 Setup & Running

#### Option A: Using `uv` (Recommended, Fast)

After cloning the repository, use **`uv sync`** to automatically create the virtual environment and install all pinned dependencies from `uv.lock`:

```bash
# 1. Clone the repository
git clone <repo-url>
cd es-housekeeping

# 2. Synchronize virtual environment & dependencies from uv.lock
uv sync

# 3. Run test suite (100% offline)
uv run pytest -v

# 4. Run CLI
uv run python es_housekeeping.py --help
```

#### Option B: Traditional Virtualenv (`pip`)

```bash
# 1. Create and activate a fresh virtual environment
python3 -m venv .venv
source .venv/bin/activate       # On Linux/macOS
# .venv\Scripts\activate        # On Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run test suite
pytest -v

# 4. Run CLI
python es_housekeeping.py report
```

---

## 5. Configuration

Configure connection and credentials via environment variables or a local `.env` file (see `.env.example`):

```bash
cp .env.example .env
```

| Variable            | Default                 | Description                                                          |
| :------------------ | :---------------------- | :------------------------------------------------------------------- |
| `ELASTIC_URL`       | `http://localhost:9200` | Base URL of the Elasticsearch HTTP API                               |
| `ELASTIC_USER`      | _(none)_                | Username for HTTP Basic Authentication                               |
| `ELASTIC_PASS`      | _(none)_                | Password for HTTP Basic Authentication                               |
| `ELASTIC_INSECURE`  | `false`                 | Set to `true` to disable TLS certificate validation (local dev only) |
| `ELASTIC_CA_BUNDLE` | _(none)_                | Path to custom CA bundle (`.pem` / `.crt`)                           |

---

## 6. Usage Examples

### 1. Cluster Index Report (Table)

```bash
python es_housekeeping.py report
```

```text
NAME                     HEALTH     DOCS  SIZE     AGE   MANAGED
-----------------------  ---------  ----  -------  ----  -------
app-config               🟢 green   12    4.2 KB   0d    No
logs-2025.01.01          🟢 green   500   24.1 KB  400d  No
reference-countries      🟢 green   250   18.5 KB  0d    No
```

### 2. Machine-Readable JSON Output (Piping with `jq`)

```bash
python es_housekeeping.py report --pattern "logs-*" --json | jq '.[].name'
```

### 3. Stale Index Preview (Dry-Run by Default)

```bash
python es_housekeeping.py cleanup --pattern "logs-*" --older-than 30
```

```text
Gefundene veraltete Indices (3, älter als 30 Tage):
...
[DRY-RUN] Es wurden keine Änderungen vorgenommen. Verwende --apply zum Schliessen.
```

### 4. Execute Safe Housekeeping (Default: Close Indices)

```bash
python es_housekeeping.py cleanup --pattern "logs-*" --older-than 30 --apply
```

```text
Möchtest du diese 3 Indices schliessen (Daten bleiben auf Disk)? [y/N]: y
Erfolgreich geschlossen: logs-2025.01.01, logs-2025.02.01
Hinweis: JVM-Heap freigegeben. Daten bleiben auf Disk erhalten.
Wiedereröffnen bei Bedarf mit: POST http://localhost:9200/logs-2025.01.01,logs-2025.02.01/_open
```

### 5. Automated Run in CI/CD / Cron

```bash
python es_housekeeping.py cleanup --older-than 90 --action delete --apply --force
```

---

## 7. Key Design Decisions & Trade-offs

### 7.1 Why `close` is the Default Action over `delete`

- **Compliance & Insurance Constraints:** In enterprise environments (audit trails, access logs, financial transaction data), compliance standards (GDPR, ISO 27001, SOC2) and insurance policies mandate long-term data retention. An irreversible `DELETE` can destroy required evidence and breach contractual obligations.
- **JVM Heap Relief vs. Disk Space:** In production clusters, the most critical bottleneck is almost always **JVM Heap and open Lucene file handles**, not raw disk storage. A closed index (`POST /{target}/_close`) completely frees its in-memory Lucene structures and heap allocation while preserving raw segments on disk.
- **Reversibility:** Closed indices can be reopened in seconds if an auditor or investigation requires them (`POST /{target}/_open`), turning maintenance from a high-risk gamble into a reversible operational task.

### 7.2 Two-Tier Age Extraction: Logical Name Date over Physical Settings

- **The Theoretical Ideal:** In an ideal world, reading `index.creation_date` from cluster settings would be the cleanest method.
- **The Real-World Pitfalls:**
  1. _Backup/Restore & Re-Indexing:_ When an old index is restored from snapshots or recreated during re-indexing, Elasticsearch sets its physical `creation_date` to the timestamp of the restore. A two-year-old log index would suddenly be evaluated as "created today".
  2. _Elasticsearch 9.4 Immutability & Seeders:_ Modern ES versions treat `index.creation_date` as private and immutable (even the provided `seed_data.py` cannot backdate it and sets identical timestamps for all seeded indices).
- **Decision:** Priority 1 extracts the logical retention date from the index name via regex (`YYYY.MM.DD`, `YYYY-MM-DD`, `YYYY_MM_DD`). Priority 2 falls back to the physical `creation_date` in cluster settings.

### 7.3 Idempotency Barrier on HTTP Retries

- The reference wrapper (`elastic_api_reference.py`) re-attempted 5xx errors indiscriminately across all HTTP methods.
- **Decision:** Automated retries with Exponential Backoff (`urllib3.util.Retry`) are strictly restricted to **idempotent `GET` requests** (`allowed_methods=["GET"]`). Non-idempotent mutations (`DELETE`, `POST /_close`) must never be automatically retried: if a packet drop occurs after the server processed the request, a blind retry could trigger split-brain states or unwanted secondary mutations.

### 7.4 Anti-Zip O(1) Dictionary Lookup per Index Name

- Elasticsearch provides no ordering guarantee between `_cat/indices` and `_settings`.
- Merging is implemented via an $O(1)$ dictionary key lookup on the unique index name (`settings_data.get(name)`), completely preventing accidental metadata misalignment.

### 7.5 Standard Library `argparse` & Exception Hygiene

- Zero framework overhead (`Click`/`Typer`).
- All operational exceptions (`ConnectionError`, `Timeout`, `HTTP 401/403`, `ValueError("SICHERHEITSALARM")`) are cleanly handled at the CLI entry point with human-readable error messages on `stderr` and POSIX-compliant exit codes (0, 1, 2, 130), eliminating raw traceback leakage.

---

## 8. What I Would Do With More Time

Due to strict time management (~5 hours invested to deliver a clean, focused, and secure MVP), the following enhancements were consciously prioritized for future iterations:

1. **Comprehensive End-to-End Integration Testing against a Multi-Node Cluster:**
   - While our unit tests achieve 100% offline isolation with mocked responses, with more time I would implement an automated integration test suite using **`testcontainers-python`** or a multi-node Docker Compose setup (3 nodes, dedicated master, multiple data tiers).
   - _Test scenarios:_
     - Verifying cluster health state transitions (`green` ➔ `yellow` ➔ `green`) during index closure.
     - Shard allocation and replica behavior when primary shards are closed.
     - Testing behavior under real network latency and transient 503 node failovers.
2. **Deeper Study of Elasticsearch Documentation & APIs:**
   - I would invest more time studying the official Elasticsearch documentation to explore advanced cluster-level monitoring APIs, optimal shard management strategies, and benchmark lightweight HTTP wrappers (`requests`) against the official `elasticsearch-py` client for long-term production maintenance.
3. **Disk-Watermark-Aware Cleanup:**
   - Integrating with `_cluster/stats` and node disk metrics. Instead of relying purely on age thresholds, the tool could trigger automated recommendations based on cluster disk watermarks (Low: 85%, High: 90%, Flood Stage: 95%).
4. **Snapshot-Before-Delete Verification Hook:**
   - Before executing a destructive `DELETE`, the CLI could query Elasticsearch Snapshot Repositories to verify that an immutable snapshot exists for the target index, aborting if no backup is found.
5. **Triage & Remediation of the AI Red-Team Security Audit (`SECURITY_AUDIT_es-housekeeping.md`):**
   - As an proactive security measure, we commissioned an extensive red-team security code audit (documented in [`SECURITY_AUDIT_es-housekeeping.md`](file:///Users/tesfa/Desktop/projects/webdev/externe-aufträge/kastgroup/es-housekeeping/SECURITY_AUDIT_es-housekeeping.md)).
   - Due to the strict 4–6 hour time budget (~5 hours invested), there was intentionally no time remaining to analyze all findings and patch the codebase in this iteration.
   - With additional time, my immediate priority would be to triage and implement the suggested hardening measures (such as preventing URL-embedded credential leakage in `ELASTIC_URL`, making `--dry-run`/`--apply` mutually exclusive CLI flags, refining ILM metadata evaluation, and adding TOCTOU index UUID re-validation before mutations).
