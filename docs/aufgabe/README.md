# Coding Exercise: Elasticsearch Index Housekeeping Tool

## Context

We run a lot of automation around Elasticsearch/Kibana. A recurring need is
**housekeeping**: clusters accumulate indices over time, and without discipline
they grow unbounded, run without a lifecycle policy, or quietly fill up disk.

Your task is to build a small, well-engineered command-line tool that inspects a
cluster, **reports** on the state of its indices, and can optionally **clean up**
stale ones according to a rule you implement.

This mirrors the kind of internal tooling we build day to day. We care much more
about how you build it than about how many features you cram in.

## The task

Build a Python CLI tool `es-housekeeping` that talks to an Elasticsearch cluster
and does the following.

### 1. Report (required)

Produce a report over the cluster's indices. For each index show at least:

- name
- health (green/yellow/red)
- document count
- primary store size (human-readable)
- age (derived from the index creation date)
- whether it is covered by an ILM policy (or, if you prefer, any other
  "is this managed?" signal you can justify)

The report must be available in **two output formats**:

- a human-readable table (default)
- machine-readable **JSON** (`--json`), suitable for piping into other automation

Support filtering, e.g. by an index-name pattern (`--pattern "logs-*"`).

### 2. Stale-index cleanup (required)

Implement a rule such as _"indices matching a pattern and older than N days are
considered stale"_ and let the tool act on them:

- `--dry-run` (this **must be the default**): report what _would_ be deleted,
  change nothing.
- `--apply`: actually delete (or close — your choice, document it) the stale
  indices.

Deleting data is destructive. We are specifically interested in how you make this
safe and hard to trigger by accident.

### 3. Configuration

The tool must be configurable for connection details (URL, credentials, TLS
verification) without editing source code — environment variables and/or a config
file are both fine. Do not hard-code secrets. Never print credentials.

## What we provide

- `docker-compose.yml` — a single-node **Elasticsearch 9.4** you can run locally.
  `docker compose up -d` and it is reachable at `http://localhost:9200`.
- `seed_data.py` — creates a handful of indices with varying ages, sizes and
  settings so you have something realistic to report on and clean up. Use it,
  adapt it, or ignore it.
- `elastic_api_reference.py` — a trimmed example of the style of API wrapper we
  use internally (basic auth, retry-on-5xx, env-var driven). **You are not
  required to use it**; it is there to show you the kind of code we write. Feel
  free to design your own client.

You are free to use any libraries you like (the official `elasticsearch` client,
plain `requests`, `httpx`, `typer`, `click`, `argparse`, ...). Justify your
choices briefly in your notes.

## Setting up a cluster is optional

If you would rather not run Elasticsearch at all, that is fine. You may develop
entirely against **mocked HTTP responses** and rely on your test suite to prove
the tool works. If you do run the provided cluster, note that in your README.
Either way, **your tests must not require a live cluster to pass.**

## Deliverables

1. Working code in a git repository (include the `.git` history — we like to see
   how you work, not just the final state).
2. A **`pytest`** test suite. Test the logic that matters: the stale-index
   decision, dry-run safety, size/age parsing, output formatting, error handling.
   Mock the HTTP layer; do not hit a real cluster in tests.
3. A **README** covering:
   - how to install and run it (assume a fresh machine + `venv`)
   - example commands and example output
   - a short **design notes** section: key decisions and trade-offs
   - a **"what I'd do with more time"** section
4. A `requirements.txt` or `pyproject.toml` so we can install cleanly.

## Ground rules

- **Using AI assistants is allowed and encouraged.** We use them too. Because of
  that, we will focus the interview follow-up on _your_ reasoning: why the code is
  structured the way it is, where the risks are, and what you would change. Be
  ready to defend and modify your solution live.
- Please work in a **virtual environment** and pin your dependencies.
- Keep it honest: if something is incomplete or untested, say so in the README.
  We far prefer a smaller, correct, clearly-scoped solution over a large one that
  doesn't run.

## Time expectation

We designed this to take roughly **4–6 hours**. Do not gold-plate it. If you find
yourself over that, stop and write down what you would have done next — that note
is part of the evaluation.

Good luck, and have fun with it.
