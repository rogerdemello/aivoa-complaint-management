# AI-Powered Customer Complaint Management System

Pharmaceutical QMS complaint intake for **API and FDF** manufacturing, built for the
AIVOA.AI Round 1 assignment.

Two panels: the **Log Customer Complaint** form on the left, the **AIVOA Copilot** on the
right. The form is never filled by hand — it is a read-only projection of state that a
LangGraph agent owns. Every value arrives through the Copilot, carrying the source text
that justified it.

**Stack:** React + Redux Toolkit · Python + FastAPI · **LangGraph** · Groq · PostgreSQL
(Supabase) · Inter

---

## Contents

- [Model availability — read this first](#model-availability--read-this-first)
- [The three mandatory tools](#the-three-mandatory-tools)
- [Architecture](#architecture)
- [Setup](#setup)
- [Demo script](#demo-script)
- [Design decisions](#design-decisions)
- [Bonus features](#bonus-features)
- [Tests](#tests)
- [Known limitations](#known-limitations)

---

## Model availability — read this first

The assignment mandates `gemma2-9b-it`. **Groq decommissioned that model on 8 October
2025.** Calling it returns `model_not_found`. The secondary model,
`llama-3.3-70b-versatile`, is also on the deprecation schedule and shuts down on
**16 August 2026**.

| Model | Announced | Shutdown | Source |
|---|---|---|---|
| `gemma2-9b-it` | 2025-08-08 | **2025-10-08** (gone) | [Groq deprecations](https://console.groq.com/docs/deprecations) |
| `llama-3.3-70b-versatile` | 2026-06-17 | **2026-08-16** | same |

Groq's per-model documentation page for `gemma2-9b-it` is stale and still implies the
model is live; the deprecations page and the `/v1/models` endpoint are authoritative.

**How this project handles it.** No graph node names a model. Nodes request a *role* —
`router`, `extractor`, `reasoner` — and `app/llm/registry.py` binds each role to a real
model at startup by probing `GET https://api.groq.com/openai/v1/models`. The
assignment-mandated IDs remain the configured defaults in `.env`; when one is missing,
the registry walks a documented fallback chain and logs the substitution loudly.

Observed on a live probe (15 models available):

```
Role router   : configured 'gemma2-9b-it' is unavailable -> using 'openai/gpt-oss-20b'
Role extractor: configured 'gemma2-9b-it' is unavailable -> using 'openai/gpt-oss-20b'
Role reasoner -> llama-3.3-70b-versatile
```

The resolution is served at `GET /api/health/models` and shown as a badge in the UI, so a
substituted model is never silent. This is also why the repo will still run after
16 August 2026, when the reasoner model disappears too.

A second consequence: **neither mandated model supports native tool calling on Groq.**
That directly shapes the routing design below.

---

## The three mandatory tools

| Tool | Trigger | Behaviour |
|---|---|---|
| **Log Complaint** | Free-text prompt | Extracts fields → fills the form → produces the risk assessment |
| **Edit Complaint** | Natural-language correction | Patches only the mentioned fields, **preserving everything else**, then re-assesses |
| **Document Extraction** | PDF / EML / TXT upload | Extracts → fills form + assessment → remains editable by natural language |

All three converge on one enrichment pipeline, so risk, completeness, CAPA and duplicate
detection behave identically regardless of how the complaint arrived.

---

## Architecture

### The graph

```mermaid
graph TD
    START([start]) --> route_intent
    route_intent -. document .-> parse_document
    route_intent -. new .-> extract_complaint
    route_intent -. correction .-> extract_patch
    route_intent -. question .-> answer_question
    parse_document --> extract_complaint
    extract_complaint --> validate_extraction
    extract_patch --> validate_extraction
    validate_extraction -. invalid, retry .-> extract_complaint
    validate_extraction -. invalid, retry .-> extract_patch
    validate_extraction -. valid .-> merge_complaint
    merge_complaint --> assess_risk
    merge_complaint --> check_completeness
    merge_complaint --> detect_duplicates
    merge_complaint --> recommend_capa
    assess_risk --> summarize
    check_completeness --> summarize
    detect_duplicates --> summarize
    recommend_capa --> summarize
    summarize --> persist --> compose_reply --> END([end])
    answer_question --> END
```

Routing is an **explicit conditional edge**, not an agentic tool-calling loop. Two
reasons: the mandated models cannot do reliable function calling, and in a GxP-regulated
context a deterministic, inspectable path is far easier to validate than a model choosing
its own control flow.

The four enrichment nodes are independent, so they run as a **parallel fan-out** and join
at `summarize`. A turn costs roughly the slowest branch rather than the sum of all four.

### Three mechanisms that carry the design

**1. Sparse-patch merge.** `extract_patch` returns *only* the fields a correction
mentions. `merge_complaint` applies them over existing state and emits a per-field diff.
Absent keys mean "not mentioned"; a `null` never clears a field. This is the behaviour the
demo explicitly requires, and the usual failure mode — an LLM re-emitting the whole object
and nulling anything it wasn't reminded of — is pinned down by tests in
`tests/test_merge.py`.

**2. Evidence-linked fields + immutable audit trail.** Every populated field carries the
verbatim source substring that justified it, visible on hover. Every change appends a row
to `complaint_field_history` recording `field, old → new, source, model, turn, timestamp`.
That is 21 CFR Part 11 §11.10(e) — a computer-generated, time-stamped audit trail that
records changes without obscuring previously recorded values — and ALCOA+ data integrity
applied to an AI-populated record.

**3. Validation with a repair loop.** Small models emit malformed JSON.
`validate_extraction` parses against Pydantic and, on failure, routes *back* to the
extractor with the validator's error appended to the prompt — up to two attempts, then it
degrades gracefully and leaves the record untouched rather than corrupting it.

**Anti-hallucination rule:** unknown fields are omitted and listed in `missing[]`. A
fabricated batch number in a GMP record is a data-integrity failure, so the extractor is
instructed to omit rather than guess, and `evidence` must be quotable.

### Layout

```
backend/
  app/
    llm/registry.py        role -> model binding + live Groq probe
    llm/client.py          chat wrapper, tolerant JSON parsing
    graph/state.py         ComplaintState, FieldValue, form definition
    graph/schemas.py       Pydantic contracts (drive the repair loop)
    graph/prompts.py       GMP/QMS domain prompts
    graph/builder.py       graph assembly
    graph/nodes/           routing, extraction, enrichment, document, persist, reply
    services/runner.py     graph lifecycle + SSE event stream
    services/duplicates.py pg_trgm similarity, rapidfuzz fallback
    db/models.py           complaints, field history, assessments, documents, messages
    api/routes/            health + complaint endpoints
  scripts/                 init_db, seed_complaints, demo_run, reset_demo
  tests/
frontend/src/
  app/api.js               SSE-over-POST reader
  app/turnThunks.js        stream events -> Redux actions
  features/                complaint, copilot, assessment, audit, session slices
  components/              form, copilot, risk, completeness, CAPA, duplicates, trace, audit
scripts/generate_samples.py
samples/
```

---

## Setup

**Prerequisites:** Python 3.12, Node 18+, a Groq API key, a PostgreSQL database.

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Linux/macOS: .venv/bin/python
cp .env.example .env                                          # then fill in the two values

# 2. Database
.venv/Scripts/python.exe scripts/init_db.py          # schema + pg_trgm + checkpoint tables
.venv/Scripts/python.exe scripts/seed_complaints.py  # historical complaints for duplicate detection

# 3. Demo documents
cd .. && backend/.venv/Scripts/python.exe scripts/generate_samples.py

# 4. Run
cd backend && .venv/Scripts/python.exe run.py        # http://127.0.0.1:8000
cd frontend && npm install && npm run dev            # http://localhost:5173
```

`.env` needs exactly two values:

```
GROQ_API_KEY=gsk_...
DATABASE_URL=postgresql+psycopg://postgres:PASSWORD@db.<ref>.supabase.co:5432/postgres?sslmode=require
```

Note the `+psycopg` in the URL scheme — SQLAlchemy needs the driver named.

> **Windows:** start the server with `python run.py`, not `uvicorn app.main:app`. psycopg's
> async mode cannot use Windows' default `ProactorEventLoop`, and uvicorn installs its own
> loop. `run.py` drives the server under a selector-policy loop instead. See
> `app/compat.py`.

> **Supabase:** the direct-connection host is IPv6-only. On an IPv4-only network, use the
> **Session pooler** connection string (port 5432) instead. Avoid the transaction pooler
> (6543) — it disables prepared statements, which LangGraph's checkpointer needs.

### Verify without the UI

```bash
cd backend
.venv/Scripts/python.exe scripts/demo_run.py   # drives all three scenarios, prints the trace
.venv/Scripts/python.exe -m pytest tests/ -q
```

---

## Demo script

Run `scripts/reset_demo.py` first — every demo run persists a real complaint, and those
accumulate as duplicate-detection noise.

### Video 1 — working demonstration

1. **Log Complaint.** Type:
   > Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules 500mg.

   The form fills progressively. Point out the source badge and hover an **evidence**
   link to show the quoted text behind a value. Risk returns **Major / High**.

2. **Edit Complaint.** Type:
   > Sorry, the batch number is BMX240602 and the affected quantity is 48 capsules.

   Only Batch/Lot Number, Quantity Affected and Unit change. Everything from turn 1
   survives. Open the **Audit Trail** to show old → new with the model attributed.

3. **Document Extraction.** Upload `samples/metformin_api_complaint.pdf`. Fourteen fields
   populate, including grade `IP/BP` and batch `MFH26C`. CAPA proposes root causes
   categorised by Ishikawa 6M; duplicate detection flags `CMP-2026-0003` as a *trend*
   (same product, different batch) rather than a duplicate.

4. **Correct the document.** Type:
   > Sorry, the batch number is CHG260712A and the affected quantity is 50 kg, 2 HDPE drums.

5. Show the **model badge** — the assignment's mandated model was decommissioned, and the
   registry substituted a live one.

### Video 2 — code walkthrough

Follow one turn end to end:

`CopilotPanel.jsx` → `turnThunks.js` → `api.js` (SSE over POST) →
`api/routes/complaints.py` → `services/runner.py` → `graph/builder.py` →
`route_intent` → `extract_patch` → `validate_extraction` (show the repair loop) →
`merge_complaint` (show the sparse-patch contract and `tests/test_merge.py`) →
the parallel fan-out → `persist` (audit rows) → back through SSE → `complaintSlice.js` →
the form re-renders.

The **LangGraph Execution** panel in the UI shows this live, node by node, with per-node
timings and the model each used.

---

## Design decisions

**Explicit routing over an agentic loop.** Neither mandated model supports Groq function
calling, and a regulated workflow benefits from a control flow you can draw and validate.

**Role-based model registry.** Nodes request capability, not identity. Cheap
classification and extraction go to a small fast model; risk, CAPA and root-cause
reasoning go to the larger one. Changing either is an `.env` edit.

**Completeness is computed, not asked.** Which mandatory fields are missing is arithmetic,
so Python does it. The model only writes *why it matters* and *what to ask the customer* —
the part that genuinely needs language. Models are unreliable at counting and good at
prose.

**One source of truth for severity.** The extractor is explicitly told not to guess
`initial_severity` or `priority`; `assess_risk` owns them and `summarize` syncs them into
the form. Without this, the form and the risk panel could contradict each other on screen.

**The reply is deterministic.** `compose_reply` narrates what the graph did from state the
code already has. Spending another model call to restate known facts would add latency and
a chance to hallucinate.

**Retrieval proposes, the model disposes.** Duplicate detection uses `pg_trgm` similarity
to shortlist candidates, then asks the model to confirm — text similarity alone reports
every complaint about the same product as a duplicate.

**The form cannot be typed into.** Enforced in state, not just markup: no input has an
`onChange` handler, and values can only arrive via a Redux action dispatched from the AI
stream.

---

## Bonus features

- **Evidence-linked extraction** — every field carries the verbatim source text
- **Immutable audit trail** — 21 CFR Part 11 §11.10(e), viewable in-app
- **AI risk classification** — GMP severity with regulatory reporting flags (e.g. FDA
  Field Alert Report, 21 CFR 314.81(b)(1), 3 working days)
- **Complaint completeness checker** — gaps with rationale and the question to ask
- **Root cause + CAPA** — Ishikawa 6M categories, correction vs corrective vs preventive,
  Phase I / Phase II investigation type
- **Duplicate detection** — trigram retrieval + model confirmation, distinguishing a
  duplicate from a trend
- **Complaint summary** — one-paragraph QA narrative for the record
- **Live LangGraph trace** — node-by-node execution in the UI
- **Model registry with live probing** — survives Groq's deprecation schedule

---

## Tests

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -q
```

Nine tests covering the highest-risk logic — the sparse-patch merge and the repair loop:
untouched fields survive an edit, nulls never clear values, unchanged values produce no
audit row, hallucinated field names are dropped, diffs carry evidence and the previous
value, malformed extractions leave the record intact, and the repair loop retries the
correct extractor before giving up.

---

## Known limitations

Stated plainly rather than discovered in the interview:

- **No OCR.** Scanned/image PDFs yield no text and are rejected with a clear message. The
  brief excludes production-grade OCR.
- **`trace` accumulates in the checkpointer** across a session rather than resetting per
  turn. Useful as session history, but it grows unbounded; the UI shows only the current
  turn.
- **Reference numbers are allocated read-then-write** (`max(suffix) + 1`) with a retry on
  unique-constraint violation. Correct under light concurrency; a Postgres sequence would
  be the production answer.
- **Schema is created with `create_all`, not Alembic.** There is no migration history to
  preserve in a fresh demo repo. Production would use Alembic.
- **No authentication.** Every audit row is attributed to `ai-copilot`. A real QMS records
  an authenticated human identity and would need Part 11 electronic signatures.
- **Extraction is non-deterministic.** Temperature is 0, but a small model occasionally
  misses a field. The completeness checker surfaces exactly what is missing, which is the
  intended mitigation rather than a claim of perfect extraction.
- **Duplicate detection scans a bounded candidate set** (25 by trigram, 300 rows in the
  rapidfuzz fallback). Fine at demo scale; a real deployment needs embeddings and an index.
