# Trade Lead Assistant (CMR)

## Agent workbench upgrade status

The same-site sales/manager workbench is being developed in stages. The implementation plan is in `docs/superpowers/specs/2026-10-26-agent-workbench-plan.md`.

Phase 1 adds the isolated `ai-assistant/agent_core` domain package with scoped read tools, pricing-version rules and policy authorization. Its 52 synthetic tests and the original 44 CRM tests pass. It is **not integrated into the existing HTTP server**: login, PostgreSQL persistence, role-based pages, real LLM calls and Wiki/RAG are still pending. The original CRM remains a local-only tool without authentication; do not expose it to untrusted users.

Run the new domain tests from the repository root with `python -m unittest discover -s ai-assistant/agent_core/tests -v`.

A local-first B2B lead-to-outreach system for a fragrance-oil export business: it turns trade-show lists and marketplace inquiries into scored customer profiles, generates outreach sequences, and tracks every follow-up — without a database, a cloud account, or a single npm/pip dependency.

The repository ships the **working application** (`ai-assistant/crm-dashboard`) plus the **agent operating rules** that drive it (`ai-assistant/AGENTS.md`, `ai-assistant/README.md`).

---

## The problem it solves

A one-person export desk runs into three recurring bottlenecks:

1. **Lead triage is subjective.** Hundreds of trade-show and Alibaba entries arrive as pasted text, with no consistent way to decide who is worth a tailored email.
2. **Inquiry text is unstructured.** Marketplace messages mix contact details, product codes, quantities and prices into one blob; copying them into a spreadsheet by hand is slow and error-prone.
3. **CRM tools leak data.** SaaS CRMs require uploading customer records to a third party, which is unacceptable when the contact list *is* the business asset.

This project answers all three with a single constraint: **the Markdown files on disk are the database.**

---

## Architecture

```text
┌────────────────────────────────────────────────────────────────┐
│  Lead sources                                                  │
│  trade-show lists · Alibaba inquiry text · CSV · pasted text    │
└───────────────────────────┬────────────────────────────────────┘
                            │  bounded collection (≤10 per run)
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  Ingestion & enrichment (agent workflow, see AGENTS.md)         │
│  · contact-info parser   name / phone / address / email         │
│  · product parser        internal code ⇄ product name columns   │
│  · ICP rubric scoring    tier A/B/C + score 0-100               │
└───────────────────────────┬────────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  Filesystem as the single source of truth                       │
│  clients/_index.md          client index                        │
│  clients/{id}.md            one profile per customer            │
│  leads/pipeline.md          status + next action per customer   │
│  output/outreach/           generated email sequences           │
└───────────────────────────┬────────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  CRM dashboard (localhost:8765)                                 │
│  Python stdlib HTTP API  →  vanilla JS SPA                      │
│  merge three sources · edit profiles · write back to Markdown   │
└────────────────────────────────────────────────────────────────┘
```

### Three-source merge

Every page load reconciles three Markdown sources instead of a database table:

| Source | Owns |
|---|---|
| `clients/_index.md` | identity and missing fields |
| `clients/{id}.md` | the authoritative customer profile |
| `leads/pipeline.md` | latest `status`, `next_action`, `updated` |

Writes go back into those same files, so the repository stays diffable, greppable and portable — `git diff` doubles as an audit log.

---

## Core capabilities

**Unstructured text → structured fields**
- `/api/contact-info/parse` splits a pasted name/phone/address block into separate fields, keeps hand-edited values from being overwritten, and logs only field names and lengths — never the raw text.
- `/api/product-info/parse` turns Alibaba inquiry tables into aligned internal-code and product-name columns, tolerating tab or multi-space column boundaries, codes with internal spaces, bracketed aliases, and trailing price/date columns. Up to 50 products per paste.

**Customer workbench**
- Two-channel views (marketplace vs. email) with independent counters, search and filters
- Custom tags persisted to the Markdown profile and indexed for search
- Draft box in `localStorage`, so a half-filled form survives an accidental close
- Client-side pagination, 15-row folding for long product lists, one-click full-column copy
- Daily checklist that never touches the CRM API or the customer files

**Operational hygiene**
- Structured error-code catalog (`CRM-CONTACT-PARSE-001`, `CRM-PAGINATION-001`, …) so every failure is greppable
- A2A handoff protocol: a second agent must read the handoff doc, the task log and the index, then append a confirmation record before it is allowed to write code

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3 standard library (`http.server`) | zero dependencies, runs from a USB stick |
| Frontend | Vanilla HTML / CSS / JS | no build step, no `node_modules` |
| Storage | Markdown files + `localStorage` | diffable, portable, no server-side DB |
| Tests | `unittest` (44 tests) + static frontend assertions | covers API contracts *and* the HTML/JS wiring |

Roughly 2,500 lines of Python, 1,450 of JavaScript, 1,300 of tests. No framework, no ORM, no package manager.

---

## Privacy by design

This repository contains **code only**. `git status` will never show a customer record:

```gitignore
/ai-assistant/clients/      /ai-assistant/leads/
/ai-assistant/output/       /ai-assistant/raw/
```

The test suite asserts both the ignore rules *and* the Git index, so a commit that accidentally tracks customer data fails CI-style checks instead of silently publishing it. A fresh clone starts with an empty customer base.

---

## Getting started

```bash
python ai-assistant/crm-dashboard/server.py
# → http://127.0.0.1:8765/
```

Options: `--host 127.0.0.1 --port 8765`.

Run the tests:

```bash
python -m unittest discover -s ai-assistant/crm-dashboard/tests -v
```

---

## Repository layout

```text
ai-assistant/
├── README.md                  lead → ICP → outreach pipeline
├── AGENTS.md                  agent operating rules and boundaries
├── crm-dashboard/             the application
│   ├── server.py              HTTP API and Markdown storage layer
│   ├── app.js                 front-end state, rendering, parsing UI
│   ├── index.html, styles.css
│   └── tests/test_server.py   44 API and front-end regression tests
├── src/                       collection config (sample only)
docs/superpowers/specs/        design specs for the pipeline and the dashboard
```

## Design docs

- `docs/superpowers/specs/2026-07-30-trade-lead-assistant-design.md`
- `docs/superpowers/specs/2026-08-27-customer-crm-dashboard-design.md`

## Scope and compliance

Lead collection is capped at roughly ten public business records per run. No captcha bypass, no account pools, no automated bulk sending — every outbound email is generated for human review and sent manually. Platform terms of service and account risk remain the operator's responsibility.
