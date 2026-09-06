# Security Audit – `es-housekeeping`

**Stand:** 2026-09-06  
**Scope:** `es_housekeeping.py` + `test_es_housekeeping.py`  
**Perspektive:** Security Audit / Red-Team-orientiertes Code Review / Requirement Review  
**Nicht geprüft:** README, `.gitignore`, `pyproject.toml`/Lockfile, Git-History, tatsächliche Elasticsearch-Rollen/Rechte, Deployment-Umgebung

---

# 1. Kurzfazit

## Gesamtbewertung: 🟠 **Gut aufgebaut, aber vor Abgabe noch einige Punkte korrigieren**

Die Sicherheitsarchitektur ist deutlich besser als in der früheren Version. Besonders positiv sind:

- ✅ Dry-Run ist Standard
- ✅ `--apply` ist für Mutationen erforderlich
- ✅ `close` ist die Standardaktion und damit reversibler als `delete`
- ✅ `delete` muss zusätzlich explizit mit `--action delete` gewählt werden
- ✅ interaktive Bestätigung vor Mutationen
- ✅ `--force` ist explizit und nicht Standard
- ✅ automatische Retries nur für `GET`
- ✅ `DELETE` und `POST /_close` werden bewusst nicht automatisch wiederholt
- ✅ TLS-Zertifikatsprüfung ist standardmäßig aktiv
- ✅ System-Indizes werden an zwei Stellen geschützt
- ✅ negative Werte für `--older-than` werden abgelehnt
- ✅ destructive Requests arbeiten mit bereits aufgelösten exakten Indexnamen und nicht direkt mit dem User-Pattern
- ✅ stdout/stderr sind sinnvoll getrennt
- ✅ Exceptions werden überwiegend sauber abgefangen
- ✅ Tests benötigen keinen Live-Elasticsearch-Cluster

**Vor der Abgabe würde ich aber mindestens die roten Findings und das fehlende explizite `--dry-run` beheben.**

---

# 2. Automatische Prüfung

## Python-Syntax

```text
python -m py_compile es_housekeeping.py test_es_housekeeping.py
→ OK
```

## Tests

Die hochgeladene Hauptdatei hieß im Chat `es_housekeeping(1).py`, während die Tests importieren:

```python
from es_housekeeping import ...
```

Nachdem die Datei für den Testlauf korrekt als `es_housekeeping.py` benannt wurde:

```text
20 passed in 0.08s
```

✅ **Alle 20 vorhandenen Tests bestehen.**

### Wichtig für die Abgabe

Im Repository muss die Datei wirklich heißen:

```text
es_housekeeping.py
```

und nicht etwa:

```text
es_housekeeping(1).py
```

---

# 3. Ampelübersicht

| Severity | Finding | Empfehlung |
|---|---|---|
| 🔴 HIGH | Alter wird primär aus dem Indexnamen statt `creation_date` berechnet | Vor Abgabe ändern oder sehr klar begründen |
| 🔴 HIGH | Credentials können über `ELASTIC_URL` in Fehlermeldungen geleakt werden | Userinfo in URL verbieten/redacten |
| 🟠 MEDIUM | Explizites CLI-Flag `--dry-run` fehlt | Vor Abgabe ergänzen |
| 🟠 MEDIUM | ILM-Erkennung `"lifecycle" in idx_settings` ist zu grob | `index.lifecycle.name` oder `_ilm/explain` verwenden |
| 🟠 MEDIUM | ILM-managed Indizes können trotzdem durch eigene Cleanup-Logik mutiert werden | Entscheidung dokumentieren oder standardmäßig ausschließen |
| 🟠 MEDIUM | Teilweise gesetzte Credentials werden stillschweigend akzeptiert | Fail-fast validieren |
| 🟠 MEDIUM | Fehlende Settings werden als `managed=False` interpretiert | Unknown/Incomplete Metadata fail-closed behandeln |
| 🟡 LOW/MEDIUM | TOCTOU zwischen Stale-Check und Delete | UUID-Revalidation als Future Hardening |
| 🟡 LOW | System-Index-Schutz basiert nur auf `.`-Prefix | Als Heuristik dokumentieren |
| 🟡 LOW | Kommentar zu HTTP-Idempotenz ist technisch nicht korrekt | Formulierung korrigieren |
| 🟡 LOW | `ELASTIC_INSECURE=true` ohne eigene explizite Warnung | Warnung auf stderr ausgeben |
| 🟡 LOW | `ELASTIC_URL` wird nicht auf `http/https` und gültige Struktur geprüft | URL validieren |
| 🟡 LOW | `Retry(total=5)` bedeutet bis zu 5 Retries zusätzlich zum ersten Versuch | README/Kommentar präzisieren |
| 🟡 LOW | Reopen-Hinweis erzeugt einen syntaktisch falschen Beispielpfad | String korrigieren |
| 🟡 TEST | Kein echter Test der Dry-Run-Sicherheitsinvariante | Unbedingt ergänzen |
| 🟡 TEST | Error-Handling wird nur teilweise getestet | 401/403/500/Timeout ergänzen |
| 🟡 TEST | Age-Prioritätsentscheidung wird nicht sicherheitsorientiert getestet | Test für „alter Name, frisch erstellt“ ergänzen |
| 🟢 GOOD | GET-only Retry + Exponential Backoff | Behalten |
| 🟢 GOOD | Mutationen ohne transparente Retries | Behalten |
| 🟢 GOOD | Default `close` statt `delete` | Sehr guter Safe Default |
| 🟢 GOOD | Exact resolved targets statt destructive wildcard | Sehr guter Blast-Radius-Schutz |
| 🟢 GOOD | Doppelter System-Index-Schutz | Defense in Depth |
| 🟢 GOOD | `--older-than` validiert `>= 0` | Behalten |
| 🟢 GOOD | TLS verify default `True` | Behalten |
| 🟢 GOOD | stdout/stderr-Trennung | Behalten |

---

# 4. 🔴 HIGH – Altersberechnung vertraut zuerst dem Indexnamen

## Aktuelles Verhalten

In `parse_index_age()` gilt:

```text
1. Datum aus Indexname
2. creation_date als Fallback
```

Beispiel:

```text
Indexname:      logs-2020.01.01
creation_date:  heute
```

Der Code bewertet ihn trotzdem als mehrere Jahre alt.

## Warum das sicherheitsrelevant ist

Ein frisch erstellter oder wiederhergestellter Index könnte einen alten Namen besitzen.

Dann entsteht:

```text
frischer Index
    ↓
alter Name
    ↓
als stale klassifiziert
    ↓
--action delete --apply
    ↓
Datenverlust
```

Das ist ein klassisches **Trust-Problem zwischen logischem Namen und tatsächlichem Metadatum**.

## Zusätzliches Requirement-Problem

Die Aufgabenstellung verlangt ausdrücklich Age aus dem **Index Creation Date**.

Der Seeder erlaubt den Namen als Fallback, falls Elasticsearch das Backdating der Creation Date nicht unterstützt.

## Empfehlung

Sicherer:

```text
1. creation_date vorhanden → verwenden
2. creation_date fehlt → Datum aus Namen als dokumentierter Fallback
3. beides fehlt → UNKNOWN / nicht destructive eligible
```

### Noch besser

Nicht einfach:

```python
return 0
```

wenn Metadaten fehlen, sondern den Zustand als unbekannt modellieren.

Beispiel:

```text
age = unknown
cleanup eligible = false
```

Das folgt dem Security-Prinzip:

> **Uncertainty reduces destructive capability.**

### Severity

🔴 **HIGH**, weil falsche Stale-Klassifikation direkt zu Delete führen kann.

---

# 5. 🔴 HIGH – Credential Leak über `ELASTIC_URL`

## Aktuelles Verhalten

Die Anwendung erwartet zwar getrennt:

```text
ELASTIC_URL
ELASTIC_USER
ELASTIC_PASS
```

aber `ELASTIC_URL` wird nicht validiert.

Ein Operator könnte daher versehentlich konfigurieren:

```text
https://user:secret@example.org:9200
```

Bei einem Connection Error wird aktuell ausgegeben:

```python
Fehler: Elasticsearch unter '{es_url}' nicht erreichbar.
```

Damit würde das Passwort auf stderr erscheinen.

## Warum das wichtig ist

Die Aufgabenstellung verlangt:

> Never print credentials.

Das wäre damit nicht unter allen akzeptierten Inputs garantiert.

## Empfehlung

Beim Laden der URL:

- nur `http` und `https` erlauben
- `username` und `password` in der URL ausdrücklich ablehnen
- Credentials nur über `ELASTIC_USER` / `ELASTIC_PASS` akzeptieren

Konzeptionell:

```python
from urllib.parse import urlsplit

parsed = urlsplit(url)

if parsed.username or parsed.password:
    raise ValueError(
        "Credentials in ELASTIC_URL are not allowed; use ELASTIC_USER/ELASTIC_PASS"
    )
```

Alternativ jede URL vor Ausgabe redakten.

**Besser ist aber, Userinfo in `ELASTIC_URL` grundsätzlich zu verbieten.**

### Severity

🔴 **HIGH**, weil es direkt eine explizite Secret-Handling-Anforderung betrifft.

---

# 6. 🟠 MEDIUM – Explizites `--dry-run` fehlt

## Aktuelles Verhalten

Dry-Run ist korrekt Standard:

```text
kein --apply
→ keine Mutation
```

Das ist sicher.

Aber:

```bash
python es_housekeeping.py cleanup --dry-run
```

liefert aktuell:

```text
error: unrecognized arguments: --dry-run
```

## Warum das relevant ist

Die Assignment-Formulierung nennt ausdrücklich:

```text
--dry-run (must be the default)
--apply
```

Die Semantik ist vorhanden, das CLI-Interface aber nicht vollständig.

## Empfehlung

Eine mutually-exclusive group:

```text
--dry-run
--apply
```

mit:

```text
default = dry-run
```

Dann gilt:

```text
keine Option       → dry-run
--dry-run           → dry-run
--apply             → mutation
--dry-run --apply   → argparse error
```

### Severity

🟠 **MEDIUM / Submission Requirement**

---

# 7. 🟠 MEDIUM – ILM-Erkennung ist zu grob

## Aktuelles Verhalten

```python
managed = "lifecycle" in idx_settings
```

Das bedeutet nur:

> Es existiert irgendein `lifecycle`-Key.

Es beweist nicht eindeutig:

> Dieser Index ist tatsächlich von einer ILM Policy verwaltet.

## Bessere Minimalvariante

```python
lifecycle = idx_settings.get("lifecycle", {})
managed = bool(lifecycle.get("name"))
```

Damit prüfst du konkret:

```text
index.lifecycle.name
```

## Semantisch sauberste Variante

Elasticsearch ILM Explain API:

```text
/{index}/_ilm/explain
```

und dort das Feld:

```text
managed
```

## Empfehlung für den Scope

Für die Take-Home reicht aus meiner Sicht:

```python
bool(idx_settings.get("lifecycle", {}).get("name"))
```

Wenn du `_ilm/explain` ohnehin schon sauber implementiert hast, ist das noch besser.

### Severity

🟠 **MEDIUM**, primär Correctness/Requirement Accuracy.

---

# 8. 🟠 MEDIUM – Managed Indices können trotzdem gelöscht/geschlossen werden

Der Report zeigt:

```text
managed = True / False
```

Die Stale-Regel berücksichtigt aber nur:

```text
age
system-index
```

Nicht:

```text
managed
```

Damit kann ein bereits durch ILM verwalteter Index zusätzlich durch dein eigenes Housekeeping geschlossen oder gelöscht werden.

## Risiko

Zwei Lifecycle-Controller wirken auf dieselben Daten:

```text
ILM
+
es-housekeeping
```

Das kann zu unerwarteten Betriebszuständen führen.

## Mögliche Entscheidungen

### Option A – Conservative Default

```text
managed=True
→ nicht automatisch cleanup eligible
```

Optional später:

```text
--include-managed
```

### Option B – bewusst erlauben

Dann im README klar dokumentieren:

> Managed status is reported for visibility, but does not exclude an index from the explicit age-based cleanup policy.

## Empfehlung

Für eine Cyber-Security-Take-Home würde ich **Option A** bevorzugen, wenn sie ohne Scope-Aufblähung machbar ist.

### Severity

🟠 **MEDIUM / Operational Safety**

---

# 9. 🟠 MEDIUM – Partial Credentials werden nicht fail-fast abgelehnt

Aktuell:

```python
username = os.environ.get("ELASTIC_USER")
password = os.environ.get("ELASTIC_PASS", "")
auth = (username, password) if username else None
```

Damit:

```text
ELASTIC_USER gesetzt
ELASTIC_PASS fehlt
→ Passwort = ""
```

und:

```text
ELASTIC_PASS gesetzt
ELASTIC_USER fehlt
→ Passwort wird ignoriert
```

## Besser

```text
beide gesetzt
→ Basic Auth

beide fehlen
→ no auth

nur eines gesetzt
→ configuration error
```

Das ist ein sauberer **fail-fast**-Ansatz.

### Severity

🟠 **MEDIUM / Configuration Hardening**

---

# 10. 🟠 MEDIUM – Fehlende Settings werden als „unmanaged“ interpretiert

Aktuell:

```python
idx_settings = settings_data.get(name, {}).get("settings", {}).get("index", {})
managed = "lifecycle" in idx_settings
```

Wenn Settings für einen Index fehlen:

```text
idx_settings = {}
managed = False
```

Damit wird aus:

```text
UNKNOWN
```

fälschlich:

```text
UNMANAGED
```

## Warum das sicherheitsrelevant ist

Bei Race Conditions, unerwarteten API-Antworten oder unvollständigen Metadaten sollte die destructive capability sinken.

Besser:

```text
managed = true / false / unknown
metadata_complete = true / false
```

und:

```text
unknown
→ nicht löschen/schließen
```

### Severity

🟠 **MEDIUM**, weil das Fail-Closed-Prinzip betroffen ist.

---

# 11. 🟡 LOW/MEDIUM – TOCTOU zwischen Analyse und Mutation

Ablauf heute:

```text
T0: Index "logs-old" wird als stale erkannt
T1: Index wird gelöscht
T2: neuer Index mit gleichem Namen wird erstellt
T3: es-housekeeping DELETE /logs-old
```

Dann könnte ein anderer Index gelöscht werden als der ursprünglich analysierte.

Das ist eine klassische:

> **Time-of-Check to Time-of-Use (TOCTOU)**

## Production-Hardening

Zusätzlich zur `name` speichern:

```text
index UUID
```

Vor Delete nochmals prüfen:

```text
name + UUID unverändert?
```

Wenn nein:

```text
ABORT
```

## Empfehlung

Nicht zwingend für die 4–6-Stunden-Take-Home implementieren.

Sehr guter Punkt für:

```text
What I'd do with more time
```

### Severity

🟡 **LOW/MEDIUM / Future Hardening**

---

# 12. 🟡 LOW – System-Index-Schutz ist eine Heuristik

Der Schutz lautet:

```python
name.startswith(".")
```

Das schützt viele Elasticsearch-System-/Hidden-Indizes, beispielsweise:

```text
.kibana...
.security...
.ds-...
```

Aber:

> `.`-Prefix ist eine Heuristik, keine semantische System-Index-Autorität.

## Positiv

Der Check existiert gleich zweimal:

```text
find_stale_indices()
+
delete_indices()/close_indices()
```

Das ist gute Defense in Depth.

## Empfehlung

Für den Take-Home-Scope akzeptabel.

Im README nicht behaupten:

> "All Elasticsearch system indices are perfectly detected."

Sondern:

> "Dot-prefixed system/hidden indices are excluded as an additional safety guard."

### Severity

🟡 **LOW**

---

# 13. 🟡 LOW – Kommentar zu HTTP-Idempotenz ist technisch falsch

Im Retry-Kommentar steht sinngemäß:

```text
POST, PUT, DELETE sind nicht idempotent
```

Das ist HTTP-semantisch nicht korrekt.

### HTTP-Semantik

```text
GET     safe + idempotent
HEAD    safe + idempotent
PUT     idempotent, aber nicht safe
DELETE  idempotent, aber nicht safe
POST    normalerweise nicht idempotent
```

## Deine Designentscheidung ist trotzdem gut

Du darfst vollkommen bewusst sagen:

> Obwohl HTTP DELETE idempotent definiert ist, retrie ich destructive housekeeping operations nicht transparent, weil ich mutation behavior explizit und vorhersehbar halten will.

Das ist sogar die stärkere Begründung.

## Empfehlung

Kommentar ändern zu:

```text
Automatic retries are restricted to GET requests. Mutating operations are intentionally not retried transparently, even where HTTP semantics are idempotent, to keep destructive behavior explicit and predictable.
```

### Severity

🟡 **LOW**, aber interviewrelevant.

---

# 14. 🟡 LOW – `ELASTIC_INSECURE=true` sollte sichtbar warnen

Sicherer Default ist bereits:

```text
verify=True
```

✅ Sehr gut.

Aber wenn gesetzt wird:

```text
ELASTIC_INSECURE=true
```

sollte die CLI ausdrücklich melden:

```text
WARNING: TLS certificate verification is disabled.
```

auf:

```text
stderr
```

Das verhindert stilles Downgrading.

### Severity

🟡 **LOW**

---

# 15. 🟡 LOW – URL-Validierung fehlt

`ELASTIC_URL` sollte mindestens validieren:

```text
scheme = http | https
hostname vorhanden
keine eingebetteten credentials
```

Dadurch werden Konfigurationsfehler früh abgefangen und rohe `requests`-Exceptions vermieden.

### Severity

🟡 **LOW / Robustness**

---

# 16. 🟡 LOW – Retry-Zahl präzise dokumentieren

Aktuell:

```python
Retry(total=5)
```

Das bedeutet:

```text
1 initial request
+ bis zu 5 retries
```

also potentiell:

```text
6 HTTP attempts
```

Nicht:

```text
5 total attempts
```

Das ist kein Security Bug.

Aber im Interview/README präzise formulieren:

> Up to five bounded retries after the initial GET request.

Zusätzlich ist der konkrete Backoff nicht einfach garantiert:

```text
0.5s, 1s, 2s ...
```

Die erste Wiederholung kann unmittelbar erfolgen; daher besser von:

```text
backoff_factor = 0.5
```

sprechen.

### Severity

🟡 **LOW**

---

# 17. 🟡 LOW – Reopen-Hinweis ist syntaktisch falsch

Aktuell wird ungefähr erzeugt:

```text
POST /http://localhost:9200/index-a,index-b/_open
```

Durch:

```python
f"POST /{es_url}/{','.join(closed)}/_open"
```

Richtig wäre beispielsweise:

```text
POST http://localhost:9200/index-a,index-b/_open
```

oder einfacher:

```text
POST /index-a,index-b/_open
```

Kein Security Finding, aber leicht vor Abgabe zu korrigieren.

### Severity

🟡 **LOW / Correctness**

---

# 18. 🟢 Sehr gute Security-Entscheidungen

## 🟢 GET-only Retries

```python
allowed_methods=["GET"]
```

Sehr gute Trennung zwischen:

```text
OBSERVE
vs.
ACT
```

Reads dürfen resilient sein; Mutationen bleiben explizit.

---

## 🟢 Selected transient 5xx

```text
500
502
503
504
```

Besser als pauschal nahezu jeden 5xx zu retrien.

---

## 🟢 Exponential Backoff

```python
backoff_factor=0.5
```

Reduziert aggressives Hammering eines bereits gestörten Elasticsearch-Clusters.

---

## 🟢 Mutationen ohne automatische Retries

`delete_indices()` nutzt bewusst:

```python
requests.delete(...)
```

und `close_indices()`:

```python
requests.post(...)
```

statt der Retry-Session.

Das ist eine klare Safety-Invariante.

---

## 🟢 Exact resolved targets statt Wildcard Delete

Sehr wichtig:

```text
User Pattern
    ↓
GET / discovery
    ↓
IndexInfo[]
    ↓
Stale Classification
    ↓
exact names
    ↓
DELETE /index-a,index-b
```

Nicht:

```text
DELETE /logs-*
```

Das reduziert den Blast Radius erheblich.

---

## 🟢 Safe Action Default

Cleanup Default:

```text
action = close
```

statt:

```text
action = delete
```

Zusätzlich:

```text
kein --apply
→ dry-run
```

Damit braucht ein irreversibler Delete aktuell mindestens bewusste Operator-Entscheidungen:

```text
--action delete
+
--apply
+
interaktive Bestätigung
```

bzw. zusätzlich explizit:

```text
--force
```

Das ist stark.

---

## 🟢 Defense in Depth für Dot-System-Indizes

Erster Schutz:

```text
find_stale_indices()
```

Zweiter Schutz direkt an der Mutation Boundary:

```text
delete_indices()
close_indices()
```

Sehr gutes Muster.

---

## 🟢 `--older-than` Input Validation

```text
-5  → rejected
0   → allowed
30  → allowed
```

Das verhindert den früheren gefährlichen Fall:

```text
age > -1
→ praktisch alles stale
```

---

## 🟢 TLS Secure Default

```text
verify=True
```

wenn keine explizite Insecure-Konfiguration gesetzt wurde.

Custom CA wird unterstützt.

---

## 🟢 stdout / stderr Separation

Report-Daten:

```text
stdout
```

Operator-/Cleanup-/Fehlermeldungen:

```text
stderr
```

Das ist insbesondere für:

```bash
es-housekeeping report --json | jq ...
```

sehr sinnvoll.

---

## 🟢 Exception Hygiene

Connection Error, Timeout, HTTP Errors, ValueError und KeyboardInterrupt werden ohne große rohe Tracebacks behandelt.

Das ist für ein CLI deutlich professioneller als ungefilterte Stacktraces.

---

# 19. Test-Audit

## Vorhandene Tests – positiv

Die Suite testet bereits:

- ✅ Byte-Formatting
- ✅ `IndexInfo` Properties
- ✅ verschiedene Datumsformate im Indexnamen
- ✅ Creation-Date-Fallback
- ✅ fehlende Altersdaten
- ✅ Retry-Konfiguration
- ✅ 404 → leere Liste
- ✅ erfolgreiches Cat/Settings-Merging
- ✅ Tabellenformatierung
- ✅ JSON-Formatierung
- ✅ Stale Filtering
- ✅ Schutz von System-Indizes
- ✅ zweite Delete-Safety-Barrier
- ✅ zweite Close-Safety-Barrier
- ✅ Close Request
- ✅ Delete Request
- ✅ `--older-than` Validierung

Das ist für einen kleinen Take-Home bereits eine brauchbare Basis.

---

# 20. 🟡 TEST GAP – Dry-Run Safety wird noch nicht wirklich getestet

Die Assignment-Anforderung nennt Dry-Run-Safety ausdrücklich als wichtigen Test.

Der aktuelle Test prüft nicht:

> Wenn `--apply` fehlt, wird garantiert weder `delete_indices()` noch `close_indices()` aufgerufen.

## Empfohlener Test

Mocke:

```text
get_indices()
delete_indices()
close_indices()
```

und setze CLI Args auf:

```text
cleanup --older-than 30
```

Dann assert:

```text
delete called = false
close called = false
```

Das ist eine der wichtigsten Sicherheitsinvarianten des ganzen Tools.

### Priorität

🟠 **Vor Abgabe sehr empfehlenswert.**

---

# 21. 🟡 TEST GAP – Delete benötigt explizites Apply

Zusätzlich sollte ein CLI-Test beweisen:

```text
--action delete
ohne --apply
→ kein DELETE
```

Und:

```text
--action delete --apply
mit Bestätigung "n"
→ kein DELETE
```

Damit testest du nicht nur Funktionen isoliert, sondern den tatsächlichen Safety Flow.

---

# 22. 🟡 TEST GAP – Error Handling

Die Aufgabenstellung nennt Error Handling ausdrücklich.

Sinnvolle Minimaltests:

```text
401 → verständliche Auth-Fehlermeldung
403 → verständliche Auth/Authorization-Fehlermeldung
500 nach Retries → non-zero exit
Timeout → non-zero exit
ConnectionError → non-zero exit
```

Nicht alle müssen unbedingt implementiert werden.

Aber mindestens **ein oder zwei echte CLI Error-Path Tests** würden die Suite deutlich stärker machen.

---

# 23. 🟡 TEST GAP – Kritische Age-Trust-Grenze

Ein besonders wichtiger Security-Test wäre:

```text
name = logs-2020.01.01
creation_date = heute
```

Frage:

```text
Soll dieser Index stale sein?
```

Mit einer sicheren Production-Policy:

```text
NEIN
```

Dieser Test würde verhindern, dass die gefährliche Name-first-Policy versehentlich wieder eingeführt wird.

---

# 24. 🟡 TEST GAP – ILM Managed Semantik

Aktuell sollte mindestens getestet werden:

```text
lifecycle.name vorhanden
→ managed = True

lifecycle fehlt
→ managed = False

lifecycle = {}
→ managed = False
```

Wenn `_ilm/explain` verwendet wird:

```text
managed:true
managed:false
```

mocken.

---

# 25. Requirement-Matrix

## Reporting

| Requirement | Status |
|---|---|
| Index name | 🟢 |
| Health | 🟢 |
| Document count | 🟢 |
| Primary store size | 🟢 |
| Human-readable size | 🟢 |
| Age | 🟠 Quelle/Policy prüfen |
| ILM managed signal | 🟠 semantisch zu grob |
| Human-readable table | 🟢 |
| JSON | 🟢 |
| Pattern filtering | 🟢 |

## Cleanup

| Requirement | Status |
|---|---|
| Pattern + age stale rule | 🟢 |
| Dry-run default | 🟢 |
| explizites `--dry-run` Flag | 🟠 fehlt |
| `--apply` | 🟢 |
| Delete oder Close | 🟢 beide vorhanden |
| Destructive Safety | 🟢 stark |

## Configuration

| Requirement | Status |
|---|---|
| URL extern konfigurierbar | 🟢 |
| Credentials extern | 🟢 |
| TLS verify konfigurierbar | 🟢 |
| Keine hard-coded Secrets | 🟢 im geprüften Code |
| Never print credentials | 🔴 URL-Userinfo Edge Case |

## Tests

| Requirement | Status |
|---|---|
| pytest | 🟢 |
| stale decision | 🟢 |
| dry-run safety | 🟠 fehlt als echter CLI-Test |
| size parsing/formatting | 🟢 |
| age logic | 🟢, aber Policy sollte geändert werden |
| output formatting | 🟢 |
| error handling | 🟠 teilweise |
| HTTP mocked | 🟢 |
| kein Live Cluster notwendig | 🟢 |

## Nicht prüfbar aus den zwei Dateien

```text
README
Git-History
Dependency Pinning
pyproject.toml / requirements.txt
.gitignore / .env handling
Least-Privilege Elasticsearch Role
```

---

# 26. Red-Team-Szenarien

## Szenario A – Frischer Index mit altem Namen

```text
logs-2020.01.01
creation_date = heute
```

Aktuell:

```text
stale
```

Mögliche Folge:

```text
delete
```

🔴 Wichtigstes Datenverlust-Szenario.

---

## Szenario B – Credentials in URL

```text
ELASTIC_URL=https://admin:secret@host:9200
```

Cluster nicht erreichbar.

Fehlerausgabe kann enthalten:

```text
admin:secret
```

🔴 Secret Exposure.

---

## Szenario C – Breites Pattern

```bash
cleanup --pattern "*" --older-than 0 --action delete --apply --force
```

Das ist sehr destruktiv, aber:

```text
pattern explizit
older-than explizit/Default-konform
action delete explizit
apply explizit
force explizit
```

Daher kein unbeabsichtigter versteckter Delete-Pfad.

🟢 Aus Security-Sicht akzeptabel, solange dies als Operator-Intent betrachtet wird.

---

## Szenario D – System-Index rutscht in interne Funktion

```text
.security-...
```

Selbst wenn `find_stale_indices()` umgangen wird:

```text
delete_indices()
→ blockiert
```

🟢 Gute Defense in Depth.

---

## Szenario E – Netzwerkfehler bei Delete

```text
DELETE wurde serverseitig ausgeführt
Response geht verloren
```

Die Anwendung retriet nicht automatisch.

🟢 Konservatives und vorhersehbares Verhalten.

---

## Szenario F – Settings-Response unvollständig

```text
Cat enthält Index A
Settings enthält Index A nicht
```

Aktuell:

```text
managed=False
age evtl. aus Namen
```

Das kann trotz unvollständiger Metadaten cleanup-eligible werden.

🟠 Sollte fail-closed werden.

---

# 27. Minimaler Fix-Plan vor Abgabe

Wenn wenig Zeit bleibt, würde ich **nur diese Punkte** machen:

## MUST FIX

1. 🔴 **Creation Date als primäre Age-Quelle verwenden**
2. 🔴 **Credentials in `ELASTIC_URL` verbieten/redacten**
3. 🟠 **`--dry-run` als echtes akzeptiertes CLI-Flag ergänzen**
4. 🟠 **ILM-Erkennung auf `lifecycle.name` oder `_ilm/explain` korrigieren**

## STRONGLY RECOMMENDED

5. 🟠 **Partial Credentials fail-fast validieren**
6. 🟠 **Dry-run Safety Test hinzufügen**
7. 🟡 **HTTP-Idempotenz-Kommentar korrigieren**
8. 🟡 **Reopen-Hinweis korrigieren**

## NICHT MEHR GOLD-PLATEN

Diese Punkte würde ich vor der Deadline eher **nur dokumentieren**:

```text
UUID / TOCTOU hardening
vollständige system-index semantic detection
komplexe Policy für ILM-managed indices
Secret Manager Integration
Monitoring / Alerting
Adaptive disk-watermark cleanup
```

---

# 28. Interview-Fragen, auf die du vorbereitet sein solltest

## Retry

> Warum retryest du GET, aber nicht DELETE?

Gute Antwort:

```text
GET is safe and idempotent. I intentionally restrict transparent retries to the read path. Although DELETE is HTTP-idempotent, destructive housekeeping operations have stronger application-level safety requirements, so failures are surfaced to the operator instead of being silently retried.
```

---

## Dry Run

> Was verhindert einen versehentlichen Delete?

Antwortstruktur:

```text
1. cleanup defaults to dry-run
2. default action is close
3. delete must be explicitly selected
4. --apply is required
5. interactive confirmation is required unless --force is explicit
6. system indices are excluded twice
7. user patterns are resolved before the destructive request
8. mutations are not transparently retried
```

---

## Pattern

> Warum nicht einfach `DELETE /logs-*`?

Antwort:

```text
Patterns are selection inputs, not mutation targets. I resolve the candidate set first, apply the stale policy locally, and only send exact index names to the destructive endpoint. That constrains blast radius and makes the dry-run output correspond to the actual targets.
```

---

## Credentials

> Warum Environment Variables / dotenv?

Antwort:

```text
The application's configuration boundary is the environment. dotenv is only a local-development convenience. Production or CI can inject the same variables from a proper secret store without changing application code.
```

---

## Close vs Delete

> Warum ist `close` Default?

Antwort:

```text
Close is the safer reversible default. It reduces the operational impact compared with irreversible deletion, while delete remains available as an explicit operator choice when disk reclamation is actually required.
```

Hinweis: Nicht übertreiben mit Aussagen wie „Close garantiert X MB Heap-Freigabe“. Besser von reduzierter aktiver Index-Nutzung bzw. reversibler Deaktivierung sprechen.

---

# 29. Finale Bewertung

## Security Design

🟢 **Gut bis sehr gut für den Scope einer 4–6-Stunden-Take-Home-Aufgabe.**

Die wichtigsten Sicherheitsentscheidungen sind nicht kosmetisch, sondern tatsächlich im Control Flow verankert:

```text
safe defaults
explicit destructive intent
defense in depth
bounded blast radius
no blind mutation retries
TLS verification
input validation
operator confirmation
```

## Größte verbleibende Risiken

```text
1. Trust in date embedded in index name
2. Potential credential leak via URL userinfo
3. Unknown metadata currently becomes false/unmanaged instead of fail-closed
4. ILM semantics are not yet precise
```

## Testqualität

🟢 **20/20 vorhandene Tests bestehen**, wenn das Modul korrekt `es_housekeeping.py` heißt.

Aber aus Security-Sicht fehlt noch der wichtigste Integrationstest:

> **Dry-run must prove that no mutation function is called.**

## Submission Readiness

### Aktueller Stand

🟠 **Fast abgabefertig.**

### Nach den vier MUST-FIX-Punkten

🟢 **Aus meiner Sicht für die Take-Home-Aufgabe gut abgabefähig.**

Danach würde ich **keine neuen Features mehr hinzufügen**, sondern:

```text
pytest
README prüfen
Git diff prüfen
Secrets prüfen
Demo einmal durchspielen
Interview-Defense vorbereiten
```

---

# 30. Letzte Pre-Submission Security Checklist

```text
[ ] Hauptdatei heißt exakt es_housekeeping.py
[ ] pytest vollständig grün
[ ] kein echtes .env committed
[ ] keine Credentials in Git-History
[ ] ELASTIC_URL enthält keine Userinfo-Credentials
[ ] creation_date ist primäre Age-Quelle
[ ] --dry-run wird explizit akzeptiert
[ ] --apply bleibt erforderlich
[ ] delete bleibt explizite Action
[ ] System-Index-Schutz vorhanden
[ ] destructive URL enthält keine Wildcards
[ ] TLS verify ist default True
[ ] ELASTIC_INSECURE wird dokumentiert
[ ] ILM managed signal ist semantisch korrekt
[ ] Dry-run Safety Test existiert
[ ] README erklärt bekannte Limitierungen ehrlich
[ ] README erklärt wichtige Trade-offs kurz
[ ] Git-History enthält keine Secrets
[ ] finaler `git diff` geprüft
```
