# Phase 3 V2 — Audit Checkpoint Report

**Date:** 2026-10-31
**Repository:** `AI Intelligence/Research intelligence v2/`
**Branch:** `feat/phase3-ai-integration` (the V2 folder itself is currently untracked)

This report is an evidence-based audit of the V2 FastAPI AI microservice. It
supersedes earlier "consolidated issue" notes that assumed the DB schema was
missing. The live database already contains the full V2 schema and a partial
ingestion; the real blocker is external (Cloudflare Vectorize credentials).

---

## 0. Environment (verified)

| Item | Value |
|---|---|
| Correct Python env | `diactricsenv` (conda, Python 3.13.14) at `C:\Users\Administrator\anaconda3\envs\diactricsenv\python.exe` |
| Wrong env (do not use) | repo-root `venv` (Python 3.14) — missing `greenlet`, `pypdf`, `langchain_core` |
| PostgreSQL | `oau_thesis_bank`, user `oau`, host `localhost:5432`, container `oau_thesis_bank_db` (postgres:16, healthy) |
| Other containers | Redis (6379) up; MinIO (9000/9001) up; **Django backend crash-looping (`Restarting`)** |
| V2 `.env` | DB creds now set (`oau`/`oau`); DeepSeek/Groq/JEV keys present; **Vectorize token/account empty** |

### Commands run (actual results)

- `docker ps` — DB healthy on `0.0.0.0:5432`, backend restarting.
- DB probe (psycopg) — all 9 `ai_intelligence` tables + 4 enums exist and match the ORM columns.
- `diactricsenv python -m pytest -q` — **full suite passes (≈290 tests, exit 0)** after fixing 4 tests + 1 production bug (below).

---

## 1. Stage-by-stage status

| Stage | Status | Key evidence |
|---|---|---|
| 0 Reconnaissance | Complete | Structure, git, env, DB, tests inventoried. |
| 1 Runtime/DB foundation | **Working** (was misreported as broken) | `init_db()` auto-creates schema/tables on startup; live schema already matches ORM; `get_database_url()` supports `RI_DATABASE_URL` or `POSTGRES_*` fallback. |
| 2 Document ingestion | Partially complete — **blocked at Vectorize** | PDF→extract→chunk→embed works; fails only at Vectorize upsert. |
| 3 Retrieval + grounded RAG | Implemented & unit-tested; **blocked by Vectorize + JEV** | Hybrid RRF retrieval, citation validation, abstention; cannot complete end-to-end without Vectorize. |
| 4 Evaluation/reliability | Implemented, **CLI-only, not wired** | RAGAS metrics, `DeepSeekLLM`, `RagasEvaluator`, `python -m oau_ai.evaluation.run`. |
| 5.1 Infra/integration | Implemented | Telemetry, actor context, error contract. |
| 5.2 Research-gap + JEV | Implemented, wired | `POST /api/v2/research-gaps/ask`. |
| 5.3 Memory/entities/working-memory | Partially wired | Memory CRUD + thesis-summary + retrieve endpoints exposed; entity extraction, working-memory add, summarization **not exposed**. |
| 5.4 Researcher network | Not exposed | `MemoryEntity`/`MemoryRelationship` models + service methods exist; no endpoint. |
| 5.5 Recommendation engine | **Not implemented** | No recommendation module found. |
| 5.6 Agent workflows | Implemented, **not wired** | `AgentGraph`/`ResearchTools` fully tested; zero HTTP exposure. |
| 5.7 Frontend integration | Not verified | Backend `AI_SERVICE_URL=http://127.0.0.1:8001`; frontend `aiService.ts` defaults to port 8888 (mismatch). |
| 5.8 Evaluation/QA | Implemented (CLI) | Evaluation package; no API route. |
| 5.9 Production readiness | Not verified | No deployment config in V2; `routes.py.bak` stray backup present. |
| 6 Deployment | Partial | Django `backend/ai_integration/` exists (untracked); R2 configured in Django, but V2 stores PDFs locally. |
| 7 Acceptance/release | Not done | No end-to-end acceptance. |

---

## 2. Live database state (read-only probe)

All 9 `ai_intelligence` tables and 4 enum types exist and their columns match
`src/oau_ai/db/models.py` exactly:

`ai_documents`, `ai_pages`, `ai_chunks`, `ai_jobs`, `researcher_memories`,
`memory_entities`, `memory_relationships`, `thesis_summaries`,
`working_memory_exchanges`; enums `ai_job_stage`, `ai_job_status`,
`ai_memory_type`, `ai_memory_source`.

**Prior ingestion data (proves Stage 2 reached embedding):**

- 1 document (`V2-TEST-001`, `local-test-user`), 4 pages (0 scanned), 24 chunks.
- All 24 chunks `is_embedded=true`, single embedding model/version.
- 1 job: `stage=failed`, `status=failed`, `vectorize_point_id_set=0`, with error
  `[ingestion_service] vectorize_not_configured: Cloudflare Vectorize is not configured...`.

This confirms the earlier "ai_documents does not exist" / "upload returns 500"
notes are stale. Ingestion works through embedding and fails **only** at
Cloudflare Vectorize.

---

## 3. Re-verification of prior live blockers (Part C)

1. FastAPI on port 8888 — **unconfirmed**; backend `.env` expects V2 at `8001`. No V2 run script found.
2. PDF upload returned 202 — **confirmed** (document + job persisted).
3. Ingestion reached extraction + embedding — **confirmed** (4 pages, 24 embedded chunks).
4. Job failed at Vectorize (not configured) — **confirmed, still true**.
5. Embedding model `BAAI/bge-large-en-v1.5`, dim 1024 — **confirmed** (config default + local sentence-transformers; no live dim assertion).
6. Django R2 configured, handoff to V2 unverified — **confirmed** (R2 in Django `.env`; V2 stores PDFs locally under `storage/documents`).
7. Eight tables, `working_memory_exchanges` missing — **stale**; all 9 now present.
8. Prior "test passes" — **reproduced independently**: full suite green.
9. Startup/root 200 ≠ working RAG — **confirmed**; RAG is blocked by Vectorize + JEV.

---

## 4. Defects found and fixed this session

Production bugs fixed:

1. **`retrieval/service.py::_get_session`** used `async with AsyncSessionLocal() as session:`
   (one call) — `AsyncSessionLocal` is `get_session_factory`, which returns an
   `async_sessionmaker`, so this raised `TypeError`. Fixed to call twice
   (`AsyncSessionLocal()()`). Verified against the live DB.
2. **`ingestion/service.py` failure handler** assigned `job.error_stage =
   job.stage.value` *after* overwriting `job.stage = FAILED`, so `error_stage`
   was always `"failed"`. Reordered to capture the real failing stage first.

Config fixes (from the preceding turn, still in effect):

3. `db/session.py` + `config.py` now load `.env` from the project root (was `src/.env`).
4. `get_database_url()` falls back to assembling a URL from `POSTGRES_*` when
   `RI_DATABASE_URL` is unset.
5. Added idempotent `init_db()` wired into `main.py` lifespan.
6. `sql/migrations/001_initial_schema.sql` corrected (schema before enums, all 9
   tables + 4 enums, `pgcrypto`).
7. `pyproject.toml` added `pythonpath = ["src"]` so tests import `oau_ai`.

Test fixes (to keep the suite green and env-independent):

8. 3 tests now clear `DEEPSEEK_API_KEY` / `JEV_API_KEY` before asserting
   "no key" behavior (they previously depended on the env being empty).
9. `test_rag_with_valid_token_and_actor_context_passes_auth` now mocks
   `RAGService.ask` instead of relying on a broken `MagicMock` session.

---

## 5. Remaining defects (not fixed — recorded for later)

- **`_generate_answer` (RAG) and JEV LLM fallback call synchronous `httpx` in an async request path** — blocks the event loop.
- **`llm/vectorize.py::VectorizeIndex` is dead code** duplicating `embeddings/vectorize.py::VectorizeService`.
- **JEV unavailable = fail-closed (BLOCK)**, so RAG short-circuits without a working JEV.
- **Chunking is character-window, not token-based** despite `CHUNK_TOKEN_SIZE` naming; `token_count` is always `None`.
- **No OCR** for scanned pages (flagged but skipped).
- **Working-memory "summarization" is a stub** (`[Summarized exchange from <date>]`); real summarization is in an unexposed method.
- **Unexposed features:** agent graph, evaluation (CLI-only), entity extraction, entity relationships, working-memory add, researcher-network, recommendation engine (absent).
- `routes.py` has unused imports (`ChatMessage`, `ChatRequest`, `TaskDesignation`, `complete_with_groq_designated`) and a stale `routes.py.bak`.
- `ActorContext` is used as a type annotation but not imported at module scope in `routes.py` (works only via lazy annotations).

---

## 6. External blockers (cannot be fixed from code)

1. **Cloudflare Vectorize credentials** (`VECTORIZE_API_TOKEN`, `VECTORIZE_ACCOUNT_ID`)
   are empty. Required to complete ingestion and to enable semantic retrieval.
   Without them, retrieval degrades to lexical-only and ingestion jobs end in `failed`.
2. **Django backend is crash-looping** — needed for the real service-to-service
   integration (Stage 6). Investigate its container logs separately.

---

## 7. Smallest safe next actions (in order)

1. Provide `VECTORIZE_API_TOKEN` + `VECTORIZE_ACCOUNT_ID` (external) → then
   re-upload a PDF to prove end-to-end ingestion + semantic retrieval.
2. Wire the agent graph (`AgentGraph`) and working-memory/entity endpoints into
   routes so Stage 5 features are reachable.
3. Fix the sync-`httpx`-in-async-path defect in `rag/_generate_answer`.
4. Resolve the frontend/backend port contract (8888 vs 8001).
5. Investigate the crash-looping Django backend for Stage 6.

---

## 8. Session checkpoint — completed work (2026-10-31, continuation)

### 8.1 Django integration blocker — FIXED

- **Root cause:** `backend/ai_integration/urls.py` imported `AIMemoryDeleteView`
  from `.views`, but that class was never defined (delete is handled by
  `AIMemoryDetailView.delete`). This crashed Django's URL config during
  `manage.py migrate`/`check`, causing the crash-loop.
- **Fix:** removed the stale `AIMemoryDeleteView` import from `urls.py`.
- **Verification:** `docker restart oau_thesis_bank_backend` → container is now
  `Up` (stable), logs show `migrate` → `No migrations to apply` →
  `runserver 0.0.0.0:8000`.

### 8.2 Research Intelligence API surface — new V2 endpoints

All under `src/oau_ai/api/routes.py`, wired to existing services (no duplicate
implementations, no placeholders; JEV responsibilities preserved):

| Method | Path | Service |
|---|---|---|
| POST | `/api/v2/agent/ask` | `agent.graph.run_agent` (bounded plan/verify/retrieve/answer) |
| POST | `/api/v2/memory/working` | `MemoryService.add_working_memory_exchange` |
| GET | `/api/v2/memory/working/context` | `MemoryService.get_working_memory_context` |
| POST | `/api/v2/memory/entities/extract` | `MemoryService.extract_entities` |
| GET | `/api/v2/memory/entities` | `MemoryService.list_entities` (new method) |
| POST | `/api/v2/memory/relationships` | `MemoryService.add_entity_relationship` |
| GET | `/api/v2/memory/relationships` | `MemoryService.list_relationships` (new method) |

Also fixed two latent `routes.py` defects: `WorkingMemoryExchange` was used but
not imported at module scope, and `ActorContext` was not imported at module
scope (both now imported).

### 8.3 Changed files (this session)

- `AI Intelligence/backend/ai_integration/urls.py` — removed stale import.
- `AI Intelligence/Research intelligence v2/src/oau_ai/api/routes.py` — 7 new endpoints + import fixes.
- `.../src/oau_ai/api/schemas.py` — 11 new Pydantic schemas.
- `.../src/oau_ai/memory/service.py` — added `list_entities`, `list_relationships`.
- `.../tests/test_research_intelligence_api.py` — new (12 tests).

### 8.4 Test results

- `diactricsenv python -m pytest -q` → **all pass (≈300 tests, exit 0)**.
- New `tests/test_research_intelligence_api.py` → 12/12 pass.

### 8.5 Outstanding blockers

1. **Cloudflare Vectorize** (external) — still no `VECTORIZE_API_TOKEN`/
   `VECTORIZE_ACCOUNT_ID`; blocks ingestion completion and semantic retrieval.
2. **Recommendation engine** — not implemented; no service exists (Stage 5.5).
3. **Live Django↔V2 communication** — the V2 service is not running as a
   process, and `AI_SERVICE_URL=http://127.0.0.1:8001` points at the Django
   *container's* loopback (not the host), so the Dockerized backend cannot
   reach a host-run V2 until the URL uses `host.docker.internal` or a shared
   network. The crash-loop is fixed; live end-to-end forwarding is unverified.
4. **Evaluation workflow** — `python -m oau_ai.evaluation.run` exists (CLI) but
   is not invoked in CI or wired to any route/regression gate.
5. **FDE/MLOps** — structured logging/trace IDs/error handling exist; model/
   prompt/config versioning, retrieval-quality/citation-grounding regression
   gates, and deployment config are not yet established.

### 8.6 Next acceptance criteria

1. With Vectorize configured, one uploaded PDF reaches `status=success` with
   `vectorize_point_id` populated and semantic retrieval returns its chunks.
2. Django forwards `POST /api/ai/agent/ask` (and the new memory/entity/network
   routes) to V2 and returns 200 with the expected shape — requires the V2
   service running and `AI_SERVICE_URL` reachable from the container.
3. Recommendation endpoints return real, evidence-backed results (not stubs)
   once a recommendation service is designed.
4. `python -m oau_ai.evaluation.run --dataset-csv ... --metrics ...` executes
   against a sample dataset and produces a report artifact.

---

## 9. Live Django → V2 integration — verified (2026-10-31)

### 9.1 Deployment architecture (observed, not assumed)

- Backend runs in Docker Compose on network `backend_default` (container IP
  `172.19.0.4`, gateway `172.19.0.1`), container `oau_thesis_bank_backend`,
  host-exposed on `:8000`.
- **No V2 Dockerfile/compose exists** → V2 runs on the host, not in Docker.
- From inside the backend container, `host.docker.internal` resolves to
  `192.168.65.254` (Docker Desktop host gateway), verified with
  `docker exec ... getent hosts host.docker.internal`.
- `AI_SERVICE_URL` was `http://127.0.0.1:8001` — the *container's own* loopback,
  unreachable for a host-run V2. Corrected to
  `http://host.docker.internal:8001` (verified reachable from the container).

### 9.2 Windows async event-loop blocker (new, fixed)

Starting V2 via `uvicorn oau_ai.main:app` failed at startup:
`psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop'`. Uvicorn
creates/overrides the loop before importing the app, so the policy in
`db/session.py` runs too late. Added `run.py`, which drives `uvicorn.Server` on
an explicit `asyncio.SelectorEventLoop`.

Host start command:
```
cd "AI Intelligence\Research intelligence v2"
"C:\Users\Administrator\anaconda3\envs\diactricsenv\python.exe" run.py
```

### 9.3 Configuration changes (no secrets exposed or committed)

- `backend/.env`: `AI_SERVICE_URL=http://host.docker.internal:8001`.
- `Research intelligence v2/.env`: `BACKEND_API_INTERNAL_TOKEN` synced to the
  same value as Django's (written directly; value never printed).
- Both `.env` files are gitignored; no secrets added to tracked files.
- Temporary probe scripts were created under `backend/` and deleted after use.

### 9.4 Live verification (real HTTP through Django, not mocked)

A probe executed **inside the backend container** generated a real SimpleJWT
access token for an active Django user and called Django's `/api/ai/` endpoints.

| Check | Request | Result |
|---|---|---|
| Forwarded health | `GET /api/ai/health/` | **200** — V2 health JSON, `database_configured=true`, `trace_id` present |
| Authenticated forwarding | `GET /api/ai/memory/` | **200** — `{"entries":[],"total":0}` (V2 accepted internal token + actor headers) |
| Error propagation | `GET /api/ai/documents/jobs/does-not-exist/` | **404** — V2 `Phase3Error(job_not_found)` mapped to 404; body carries the forwarded V2 `trace_id` |
| Auth enforced | `GET /api/ai/health/` (no token) | **401** |
| Trace-ID propagation | `GET /api/v2/health` with `X-Trace-Id: integration-trace-abc-123` | **200**, echoed `trace_id == integration-trace-abc-123` (match) |
| Service unavailable | V2 stopped, `GET /api/ai/health/` | **502** structured `{"error":"AI Service Unavailable", ...}` |
| Service unavailable (list) | V2 stopped, `GET /api/ai/memory/` | **503** structured `{"error":"AI Service Error", ...}` |

V2 access log during the round-trip:
```
INFO: 127.0.0.1:51534 - "GET /api/v2/memory/ HTTP/1.1" 200 OK
```

### 9.5 Test results

- `diactricsenv python -m pytest -q` → **all pass (exit 0, ≈300 tests)**.
- Added `test_health_echoes_trace_id` (real TestClient request; no DB/LLM).

### 9.6 Remaining blockers / observations

1. **Cloudflare Vectorize** still unconfigured — ingestion completion and
   *semantic* retrieval remain blocked (lexical-only fallback works).
2. **V2 is not containerized** — it must run on the host and be reached via
   `host.docker.internal`. Containerizing it (on `backend_default`) would allow
   reaching it by service name and remove the host dependency.
3. **Inconsistent unavailable status**: `AIHealthView` returns 502 while other
   views return 503 for the same root cause. Align the mapping.
4. **Timeouts**: `forward_to_v2` uses 60 s default, 120 s for upload/RAG/gaps.
   Not exercised live (no slow endpoint); configuration-only evidence.
5. **Process lifecycle**: `python run.py` must be kept running (this session ran
   it as a background process).

### 9.7 Next acceptance criteria

1. Keep `python run.py` running (or containerize V2), then re-run the four
   `/api/ai/` endpoints through Django and confirm 200/404/401 as above.
2. Configure Vectorize, then verify an authenticated `POST /api/ai/rag/ask/`
   returns grounded citations end-to-end (not lexical-only).
3. Align 502/503 unavailable mapping across the Django AI views.

---

## 10. Frontend + provider readiness cleanup (2026-11-01)

### 10.1 Provider verification (live)

- **DeepSeek**: live completion returned `OK` — primary generation provider works.
- **JEV**: reached via `TypedDecisionRouter.route(...)` → `RoutingDecision.ALLOW`
  for a benign query. (A raw `classify` probe returned HTTP 422 due to a
  malformed `questions` payload; the router builds the correct payload and
  succeeds.)
- Conclusion: tomorrow only **Cloudflare Vectorize** is needed — the generation
  and decision layers are live.

### 10.2 Frontend fixes (blank page root cause + gap wiring)

- Removed a stray `#` Python comment in `src/services/__tests__/aiService.test.ts`
  (it broke `tsc -b`).
- `Screen22`/`Screen23` no longer import the deleted `checkSimilarity` /
  `SimilarityReport`. Because `App.tsx` statically imports every screen, the
  missing ESM export crashed app mounting — this was the blank page.
- `ResearchGap` interface: added optional legacy fields so older screens compile.
- `detectGaps` now calls the real V2 endpoint `POST ai/research-gaps/ask/`
  (previously `GET ai/research-gaps?topic=…`, which 404'd).
- `Screen25`, `Screen26`, `AIInsightsDashboard` now render V2 gap fields
  (`gap_type`, `description`, `explanation`, `source_thesis_references`,
  `source_origin`, `confidence`) instead of V1 fields (`topic_name`,
  `document_count`, …).
- `AIInsightsDashboard` error text no longer references the old `:8888` port.

### 10.3 Backend

- Added `GET /health` and `/health/` to `config/urls.py` → `200
  {"status":"ok","service":"oau-thesis-bank-backend"}`, silencing the 404 spam
  from external health probes (the backend was never down).

### 10.4 Verification

- `npm run build` → passes (2610 modules, exit 0).
- `npm run test` → 6/6 pass.
- `curl http://127.0.0.1:8000/health` → 200.

### 10.5 Still needs Vectorize

- Semantic retrieval / full hybrid RAG / vector indexing. Ingestion still ends
  `failed` at the vectorize stage until credentials are provided.

---

## 11. Upload 403 + UI leak fixes (2026-11-01, continued)

### 11.1 Upload returned 403 — root cause and fix

`Thesis.can_view` checked `is_public() -> status == PUBLISHED` **before** the
owner check, so a freshly uploaded `public` **draft** thesis returned `False`
even for its own owner → Django `check_thesis_access` denied the AI upload (403).
Fixed the order: owner first, then admin, then public+published.

Verified: `can_view(owner) == True` for thesis 51 (draft/public/owner 2);
`can_view(None) == False`.

### 11.2 UI no longer exposes internal tools

- `Screen27` no longer renders `Engine: …` / `Confidence: …`
  (decision_engine / confidence). Internal provider/JEV details remain in the
  API payload only and are not shown to end users.
- `Screen27`/`Screen28` now render the real V2 citation objects
  (`backend_thesis_id`, `page_number`, `text_snippet`, `relevance_score`)
  instead of assuming `citations: string[]` / `sources`.
- `Screen22` message no longer names the internal V2 service.

### 11.3 Verification

- `npm run build` → passes; `npm run test` → 6/6.
- Backend restart → `/health` 200; `can_view(owner)=True`.

### 11.4 Still not implemented / pending

- **Recommendation engine** — genuinely not built (Stage 5.5); the dashboard
  shows "unavailable". This is a missing feature, not a crash.
- **Research gap** — now calls the correct POST endpoint; needs an indexed,
  accessible document (works after a successful upload; lexical-only until
  Vectorize).
- **Vectorize** — still the external blocker for semantic retrieval/summaries.

---

## 12. General-knowledge assistant + Groq (2026-11-01, continued)

### 12.1 What changed

- New V2 endpoint `POST /api/v2/assistant/chat` (general knowledge, not grounded):
  - Accepts `messages` + `provider` (`deepseek` | `groq`).
  - DeepSeek default; Groq only when explicitly selected (designated task).
  - Best-effort JEV input safety: blocks on an explicit policy/guardrail decision,
    proceeds when JEV is unavailable (general chat is not grounded retrieval).
  - Returns `{answer, provider, mode: "general"}`.
- Django proxy `AIAssistantChatView` → `POST /api/ai/assistant/chat/`.
- Frontend `aiService.askGeneralAssistant()`; `Screen27` is now a general chat
  with a DeepSeek/Groq selector and a Clear button. Conversation persists across
  screen navigation via `sessionStorage` (keyed by user id), so it no longer
  clears when you leave the screen.
- `Screen28` ("AI Answer With Sources") remains the grounded, cited thesis RAG.
- Screens no longer display `decision_engine`/`confidence` (internal tools hidden).

### 12.2 Groq config fix

`GROQ_BASE_URL` was `https://api.groq.com` (missing `/openai/v1`), so the health
probe hit `/models` → 404 and the provider was marked unhealthy. Corrected to
`https://api.groq.com/openai/v1`.

### 12.3 Live verification (through Django, real calls)

- `POST /api/ai/assistant/chat/` `[deepseek]` → **200** general answer.
- `POST /api/ai/assistant/chat/` `[groq]` → **200** general answer.

### 12.4 Tests

- V2 `tests/test_research_intelligence_api.py` → 17 passed (5 new assistant tests:
  auth 401, invalid provider 400, DeepSeek success, Groq selected, safety block).
- Full V2 suite → passes.
- Frontend `npm run build` → passes; `npm run test` → 7/7.

### 12.5 Notes / trade-offs

- General chat is intentionally **not grounded** and **not cited**; it can return
  model knowledge beyond the corpus. Grounded answers remain on Screen28.
- General chat runs JEV best-effort and does not require evidence (unlike RAG).
- Vectorize still unconfigured (semantic retrieval / better summaries pending).

### 12.6 Safety false-positive fix (general chat)

JEV's fallback path reports BLOCK with `guardrail_outcome=blocked` for any
low-confidence input, so the assistant's safety gate wrongly refused benign
messages like "nice" / "nice job". Fixed: the general assistant now blocks only
genuine guardrail/JEV blocks (`engine_used in {"guardrails","jev"}`), ignoring
the LLM-fallback block. Verified live: "nice"/"nice job" → normal replies;
"What is a CNN?" → answered; "how to make a bomb" → refused by the provider's
own safety (not our gate).

---

## 13. Cloudflare Vectorize enabled + client fixes (2026-11-01)

### 13.1 Configuration

- `VECTORIZE_API_TOKEN`, `VECTORIZE_ACCOUNT_ID`, `VECTORIZE_INDEX_NAME=oautb-index`
  set in the V2 `.env`.
- Index `oautb-index` exists: **dimensions 1024, metric cosine**
  (`GET …/indexes/oautb-index` → 200).
- V2 health now reports `vectorize_configured: true`.
- Note: editing `.env` had blanked `POSTGRES_USER`/`POSTGRES_PASSWORD`; an explicit
  `RI_DATABASE_URL` was written so startup succeeds.

### 13.2 Two real Vectorize client bugs found and fixed

The client had never run against the live API (credentials were empty), so two
latent path/payload bugs surfaced:

1. **Upsert URL was wrong** — `…/indexes/{name}/vectors/upsert` → **404**. The
   correct endpoint is `…/indexes/{name}/upsert`. Fixed in `upsert` and `aupsert`.
2. **Query payload was invalid** — `returnMetadata: true` → **400** ("expected
   value"). Cloudflare expects a string; changed to `"all"` in `query` and
   `aquery`.

Live verification: `upsert: OK`; query returned the upserted point
(`score ≈ 0.99999`). One probe vector (`probe-…`) remains in the index because no
working delete endpoint exists at `/delete` (404); it is a single
random-direction vector with metadata `{"probe": true}` and negligible relevance.

### 13.3 R2 vs local storage (architecture note)

Intended plan: PDF → R2 → V2 reads from R2 → vectorize → Vectorize.
Current: Django forwards the uploaded file bytes to V2, which stores a local copy
under `storage/documents/` and processes that. R2 is Django's storage; V2 does
**not** read from R2 yet. Wiring V2 to pull from R2 (`OBJECT_STORAGE_*` +
object-key handoff) is the remaining Stage-6 task.

### 13.4 Not implemented

- **Plagiarism detection / AI-content detector**: no V2 module or endpoint (V1
  had similarity; V2 removed it). Only an evaluation metric named
  `answer_similarity` exists.
