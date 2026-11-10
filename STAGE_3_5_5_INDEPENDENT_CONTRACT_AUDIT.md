# OAU THESIS BANK — STAGE 3.5.5 INDEPENDENT CONTRACT AUDIT

**Status:** Independent engineering review (audit only). No production code modified. No test users/documents created. No destructive operations executed. No live tests run — nothing here is "LIVE TEST VERIFIED." Stage 3.6 not started.

**Scope:** Registration, login, thesis creation, PDF upload, ingestion job status, extracted text retrieval, similarity search, normal research retrieval (RAG), document deletion, Vectorize deletion.

**Verification levels used:**
- **CODE VERIFIED** — confirmed by reading the actual source file and line range.
- **UNIT TEST VERIFIED** — an existing unit test (mocked, not live) covers the behavior.
- **LIVE TEST VERIFIED** — confirmed against a running server. *None in this report.*
- **NOT VERIFIED** — not confirmed by code, test, or live run.

---

## 1. Verified endpoint contracts

All Django-mediated AI routes are mounted under `/api/ai/` (`backend/config/urls.py:33`) and proxy to the V2 FastAPI service at `AI_SERVICE_URL` (`backend/config/settings.py:207`) using an internal service token (`BACKEND_API_INTERNAL_TOKEN`, settings.py:209). Django is the identity/permission authority; the browser's JWT is never forwarded to V2 (`ai_integration/views.py:4-10`).

### 1.1 Registration — POST /api/auth/register/
- **File:** `backend/accounts/views.py:26-44` (`RegisterView`), `backend/accounts/urls.py:13`
- **Auth:** `AllowAny` (no auth required)
- **Request:** JSON `{email, password (min 8), name, role, department, faculty}`. `role == "admin"` is rejected (`serializers.py:33-35`).
- **Response 201:** `{user, access, refresh}` (JWT pair via `RefreshToken.for_user`, views.py:36-44)
- **DB:** creates `accounts.User` (email is `USERNAME_FIELD`, models.py:57)
- **Verification:** CODE VERIFIED

### 1.2 Login — POST /api/auth/login/
- **File:** `backend/accounts/urls.py:14` (`TokenObtainPairView` from `rest_framework_simplejwt`)
- **Auth:** `AllowAny`
- **Request:** JSON `{email, password}`
- **Response:** `{access, refresh}` JWT
- **Verification:** CODE VERIFIED

### 1.3 Thesis creation — POST /api/theses/
- **File:** `backend/theses/views.py:53-122` (`ThesisViewSet`), `backend/theses/urls.py:6-7`
- **Auth:** `IsAuthenticatedOrReadOnly, IsActiveUser` (views.py:54); write requires authenticated + active user
- **Request:** multipart/form-data via `ThesisSerializer` (`backend/theses/serializers.py:32-121`). Fields: `title, author, department, faculty, year, abstract, supervisor, tags (list), status, access_policy, file`.
- **File rules:** `file` is write_only (serializers.py:68), PDF only, ≤10 MB (`validate_file`, serializers.py:97-102)
- **Owner:** auto-set to `request.user` in `create` (serializers.py:106); not client-supplied
- **Response:** `ThesisSerializer` data; creates `Thesis` row (serializers.py:109)
- **Verification:** CODE VERIFIED

### 1.4 PDF upload (ingestion start) — POST /api/ai/documents/upload/
- **File:** `backend/ai_integration/views.py:95-167` (`AIDocumentUploadView`), `backend/ai_integration/urls.py:35`
- **Auth:** `IsAuthenticated, IsActiveUser`
- **Request (multipart/form-data):** `file` (PDF), `backend_thesis_id` (required), `thesis_metadata` (optional JSON string). Client must NOT send `backend_user_id` or `access_level`.
- **Server derivation (NOT client-chosen):**
  - `backend_user_id = str(request.user.id)` (views.py:142)
  - `access_level = derive_access_level(thesis_id, request.user)` (views.py:127; services.py:123-149) — derived from the Django Thesis record; a non-published thesis is forced to `"private"`
- **Forwards to:** V2 `POST /api/v2/documents/upload` (`forward_to_v2`, services.py:156-164)
- **V2 contract:** `src/oau_ai/api/routes.py:140-218`. Form fields `file, backend_thesis_id, backend_user_id, access_level, thesis_metadata`. Validates `.pdf` suffix and `access_level in {public,restricted,private}` (routes.py:164-169). Creates `AIDocument` + `AIJob` (status PENDING), queues background ingestion, returns 202 `{document_id, job_id, status, message}` (routes.py:213-218).
- **Verification:** CODE VERIFIED. UNIT TEST VERIFIED — backend `tests_p2.py:84` (`test_upload_ignores_client_supplied_access_level`) and `:108` (`test_upload_forwards_published_public_level`); V2 `test_api.py:53` (`test_upload_without_service_token_returns_401`).

### 1.5 Ingestion job status — GET /api/ai/documents/jobs/{job_id}/
- **File:** `backend/ai_integration/views.py:170-202` (`AIJobStatusView`), `backend/ai_integration/urls.py:36-40`
- **Auth:** `IsAuthenticated, IsActiveUser`
- **Forwards to:** V2 `GET /api/v2/documents/jobs/{job_id}` (routes.py:253-305)
- **Status aliasing:** V2 terminal state `"success"` is mapped to `"completed"` for the frontend (`views.py:37, 196-199`)
- **Response:** `{job_id, status, stage, message, result, error_message, error_stage, attempts, max_attempts}`; `result` populated only when `status == "success"` and document exists (routes.py:277-282)
- **Access:** only document owner or admin (`ingestion/service.py:650-660`)
- **Verification:** CODE VERIFIED. UNIT TEST VERIFIED — backend `tests_p0.py:108`, `tests_p1.py:152`; V2 `test_job_status_session.py`.

### 1.6 Extracted text retrieval — GET /api/ai/documents/{internal_document_id}/text/
- **File:** `backend/ai_integration/views.py:246-275` (`AIDocumentTextView`), `backend/ai_integration/urls.py:41-45`
- **Auth:** `IsAuthenticated, IsActiveUser`
- **Path param:** `internal_document_id` = V2 `AIDocument.id` (UUID), NOT the Django thesis id
- **Forwards to:** V2 `GET /api/v2/documents/{internal_document_id}/text` (routes.py:420-479)
- **V2 access:** only `document.backend_user_id == actor.user_id` or admin; else 403 (routes.py:443-447)
- **Response:** `{document_id, backend_thesis_id, pages[{page_number, text, char_offset_start, char_offset_end, is_scanned}], total_characters, total_pages}` (routes.py:464-479)
- **Verification:** CODE VERIFIED

### 1.7 Similarity search — POST /api/ai/similarity/check/
- **File:** `backend/ai_integration/views.py:532-570` (`AISimilarityCheckView`), `backend/ai_integration/urls.py:73-77`
- **Auth:** `IsAuthenticated, IsActiveUser`
- **Request:** JSON `{text, min_score?, max_matches?, exclude_document_ids?, enable_semantic?}`
- **Forwards to:** V2 `POST /api/v2/similarity/check` (routes.py import of `SimilarityService`; `SimilarityService.compare_text`, `src/oau_ai/similarity/service.py:169-262`)
- **V2 behavior:** lexical 5-shingle containment against accessible chunks (`_build_access_conditions`, `retrieval/service.py:111-124`); optional semantic via Vectorize (`_semantic_matches`, similarity/service.py:294-366) which is **degraded to lexical-only** when Vectorize is not configured (similarity/service.py:298-310). Never a plagiarism verdict (`PlagiarismAssessmentService`, similarity/service.py:369-448).
- **Response:** `{input_mode, passages_scanned, chunks_scanned, matches[], exact_matches[], semantic_matches[], limitations[]}`
- **Verification:** CODE VERIFIED. UNIT TEST VERIFIED — `test_api_route_wiring.py:60` (`test_similarity_route_is_wired`).

### 1.8 Normal research retrieval (RAG) — POST /api/ai/rag/ask/
- **File:** `backend/ai_integration/views.py:309-374` (`AIRAGAskView`), `backend/ai_integration/urls.py:56`
- **Auth:** `IsAuthenticated, IsActiveUser`
- **Request:** JSON `{question, document_ids?, top_k? (default 5)}`
- **Forwards to:** V2 `POST /api/v2/rag/ask` (routes.py:482-565)
- **V2 behavior (`RAGService.ask`, `src/oau_ai/rag/service.py:227-384`):** (1) JEV classification gate; (2) verify document access (`verify_access_before_retrieval`); (3) hybrid retrieval — dense Vectorize (`_query_vectorize`, rag/service.py:438-482) fused with PostgreSQL full-text (`RetrievalService.hybrid_retrieve`, `src/oau_ai/retrieval/service.py:547-677`) via RRF (`rrf_fuse`, retrieval/service.py:81-108); (4) optional cross-encoder rerank; (5) DeepSeek answer generation (primary, no Groq fallback, rag/service.py:545-552); (6) citation validation against actual evidence (`_validate_citations`, rag/service.py:560-620); (7) structured abstention if insufficient evidence.
- **Response:** `{answer, citations[{chunk_id, document_id, backend_thesis_id, text_snippet, page_number, section, relevance_score}], confidence, decision_engine, llm_tier, trace_id, request_id, insufficient_evidence, message, abstention_reason}`
- **Verification:** CODE VERIFIED. UNIT TEST VERIFIED — `test_p2_retrieval_security.py` (access/degraded behavior), `test_hybrid_retrieval.py`.

### 1.9 Document deletion — DELETE /api/ai/documents/{backend_thesis_id}/
- **File:** `backend/ai_integration/views.py:205-243` (`AIDocumentDeleteView`), `backend/ai_integration/urls.py:51-55`
- **Auth:** `IsAuthenticated, IsActiveUser`
- **Path param:** `backend_thesis_id` — the **Django Thesis primary key** (not the internal V2 document UUID). Confirmed by `check_thesis_write_access(backend_thesis_id, request.user)` (views.py:223) which does `Thesis.objects.get(id=thesis_id)`.
- **Forwards to:** V2 `DELETE /api/v2/documents/{backend_thesis_id}` (routes.py:308-330)
- **V2 behavior (`IngestionService.delete_document`, `src/oau_ai/ingestion/service.py:664-719`):** looks up `AIDocument` by `backend_thesis_id`; access check (owner/admin); collects `vectorize_point_id`s; deletes source file; deletes `AIDocument` row (cascades to `AIPage`, `AIChunk`, `AIJob` via SQLAlchemy cascade/db ON DELETE CASCADE, db/models.py:86-105,119-145,164-171,206-219); then `_delete_vectors(point_ids)` (service.py:713).
- **Response:** 200 `{"detail": "Document <id> deleted."}` (routes.py:330)
- **Verification:** CODE VERIFIED. UNIT TEST VERIFIED — `test_ingestion_reliability.py:308` (`test_delete_document_removes_vectors`).

### 1.10 Vectorize deletion
- **No standalone endpoint exists.** Vectorize deletion happens only as a best-effort step inside document deletion (`IngestionService.delete_document` → `_delete_vectors`, service.py:278-292, called at service.py:713).
- **Vectorize client:** `VectorizeService.adelete` → Cloudflare `index_url + "/delete_by_ids"` (`embeddings/vectorize.py:151-184`). `aupsert` → `/upsert` (vectorize.py:116-149); `query` → `/query` (vectorize.py:186-228).
- **Failure handling:** `_delete_vectors` catches **all** exceptions and logs a warning; it does **not** raise (`ingestion/service.py:289-292`). DB rows are deleted before Vectorize is called, so a Vectorize failure leaves orphaned points but does not fail the HTTP response.
- **Consequence:** HTTP 200 from document deletion is **not** proof that Vectorize deletion completed. It only proves Django-side rows + file were removed.
- **Verification:** CODE VERIFIED. UNIT TEST VERIFIED — `test_ingestion_reliability.py:343` (`test_vectorize_adelete_posts_point_ids`), `:358` (`test_vectorize_adelete_requires_configuration`), `:370` (`test_vectorize_adelete_noop_without_ids`).

---

## 2. Actual data model relationships

### Django (PostgreSQL, public schema)
- `accounts.User` (`backend/accounts/models.py:35-65`): email `USERNAME_FIELD`, `role` (student/researcher/faculty/admin, default student), `status` (active/suspended/pending, default active), department, faculty. One user owns many theses.
- `theses.Thesis` (`backend/theses/models.py:16-96`): `owner` FK → User; `status` (draft/processing/published/flagged); `access_policy` (public/restricted/private); `processing_status`; `file` (FileField, PDF); `tags` M2M → `Tag`. One thesis has many `AccessRequest`s and `SavedThesis`s.
- `theses.AccessRequest` (models.py:108-121): `thesis` FK, `requester` FK, status pending/approved/denied.
- `theses.SavedThesis` (models.py:99-105): `user` FK, `thesis` FK, unique_together.

### V2 AI service (PostgreSQL, `ai_intelligence` schema, SQLAlchemy)
- `src/oau_ai/db/models.py`:
  - `AIDocument` (models.py:52-105): `id` (UUID PK), `backend_thesis_id` (String, **unique**, indexed — links to Django Thesis PK, **no DB-level FK**), `backend_user_id` (String), `object_key`, `file_hash`, `access_level` (public/restricted/private), `embedding_status`, `thesis_metadata` (JSON). Cascades to pages/chunks/jobs.
  - `AIPage` (models.py:108-150): `document_id` FK → `ai_documents.id`.
  - `AIChunk` (models.py:153-198): `document_id` FK, `page_id` FK, `vectorize_point_id` (String, unique — maps chunk → Vectorize point), `is_embedded`, `embedding_model/version`.
  - `AIJob` (models.py:200-261): `document_id` FK, `status` (pending/processing/success/failed), `stage` (extraction/chunking/embedding/vectorize/complete/failed).
- Relationship: one `AIDocument` has many `AIPage`s, `AIChunk`s, `AIJob`s. `backend_thesis_id` is the semantic link back to Django `Thesis.id`, enforced at the API/permission layer (not referential integrity).

---

## 3. Actual document and thesis ID semantics

| ID | Type | Where it lives | Semantics |
|---|---|---|---|
| Django `Thesis.id` | BigAutoField (int) | `theses.Thesis.id` | The thesis record. |
| `backend_thesis_id` | String | V2 `AIDocument.backend_thesis_id` (unique) | The Django Thesis PK passed through as a string. **Must reference an existing thesis** — `derive_access_level` and `check_thesis_write_access` both do `Thesis.objects.get(id=thesis_id)` and return None/False if missing → 403 (`ingestion/services.py:132-135, 111-114`). No DB FK enforces this. |
| `AIDocument.id` | UUID | V2 `ai_documents.id` | Internal V2 document record. Created per upload (`uuid.uuid4()`, ingestion/service.py:141). |
| `AIJob.id` | UUID | V2 `ai_jobs.id` | Internal ingestion job. |
| `AIChunk.id` / `vectorize_point_id` | UUID | V2 `ai_chunks.id` / `ai_chunks.vectorize_point_id` | Chunk row and its Vectorize point mapping. |

**Resolution of uncertainty D:** The document deletion endpoint expects `backend_thesis_id` (Django Thesis PK), passed as the URL path parameter (`DELETE /api/ai/documents/{backend_thesis_id}/`). It is **not** the internal V2 `AIDocument.id`. The previous script's confusion of document IDs and thesis IDs is invalid.

**Frontend confirmation (uncertainty C):** The frontend uploads to `ai/documents/upload/` against base `http://127.0.0.1:8000/api`, i.e. `POST /api/ai/documents/upload/` (`frontend/src/services/aiService.ts:58`). The frontend deliberately does **not** send `backend_user_id` or `access_level` (aiService.ts:57 comment), matching the server-side derivation.

---

## 4. Ingestion lifecycle

1. **Upload** (`POST /api/ai/documents/upload/`): Django validates `backend_thesis_id` exists and user is owner/admin (`derive_access_level`), derives `backend_user_id` and `access_level`, forwards multipart to V2. V2 stores the PDF to a temp file, creates `AIDocument` (embedding_status=pending) + `AIJob` (status=PENDING, stage=EXTRACTION), queues background ingestion, returns 202 `{document_id, job_id, status}`.
2. **Duplicate guard:** if an `AIDocument` with that `backend_thesis_id` already exists and its latest job is not FAILED, upload raises `document_already_exists` (V2 409 → Django `ingestion/service.py:108-116`). Only a FAILED job may be retried (`_reingest_existing`, which purges derived data first, service.py:192-250).
3. **Background pipeline** (`IngestionService.process_job`, service.py:316-443): extraction (pypdf, `document_processing/extraction.py`) → chunking (`document_processing/chunking.py`, ~512 char chunks) → embedding (`EmbeddingService`, sentence-transformers BGE) → Vectorize upsert (`VectorizeService.aupsert`) → mark `embedding_status=completed`, job status=SUCCESS. **Never marks SUCCESS unless all stages complete**; on failure sets status=FAILED with `error_stage`/`error_message` (service.py:429-443).
4. **Vectorize confirmation:** `_assert_upsert_confirmed` (service.py:294-314) refuses success unless Vectorize confirms `success == true` and `count >= expected`; otherwise raises `ProviderUnavailableError` and the job fails.
5. A PDF with no extractable text fails at extraction with `no_extractable_text` (service.py:368-377) — scanned/empty PDFs cannot be indexed (no OCR).

**Verification:** CODE VERIFIED. UNIT TEST VERIFIED — `test_ingestion.py` (create/duplicate/access/failure), `test_ingestion_reliability.py` (partial upsert confirmation fails ingestion, line 175), `test_configuration_error_consolidation.py:167` (vectorize never called after embedding failure).

---

## 5. Retrieval lifecycle

Two **separate** operations (resolves uncertainty F):

### 5.1 Similarity search (`POST /api/ai/similarity/check/`)
- V2 `SimilarityService.compare_text`: lexical 5-shingle containment of submitted passages against chunks the actor may access (`_build_access_conditions`). Optional semantic via Vectorize query, degraded to lexical-only if unconfigured. Returns matches with `match_type` (exact/near_exact/partial/semantic), scores, excerpts. No plagiarism verdict — `PlagiarismAssessmentService` only interprets.

### 5.2 Normal research retrieval / RAG (`POST /api/ai/rag/ask/`)
- V2 `RAGService.ask`: JEV gate → verify document access → hybrid retrieval (Vectorize dense + PostgreSQL FTS fused by RRF) → optional rerank → DeepSeek generation from retrieved evidence only → citation validation → structured abstention if confidence < 0.50.

**Access model (both):** `RetrievalService._build_access_conditions` (`retrieval/service.py:111-124`): actor sees documents where `access_level == "public"` OR `backend_user_id == actor.user_id`; admins see all levels. Document-level access is enforced **before** any chunk text is returned; Vectorize metadata is treated as a hint, never authority (`resolve_authorized_chunks`, retrieval/service.py:325-362).

**Verification:** CODE VERIFIED. UNIT TEST VERIFIED — `test_p2_retrieval_security.py`, `test_hybrid_retrieval.py`.

**Unresolved (uncertainty G):** There is **no endpoint** to verify that a particular document's chunks were actually indexed in Vectorize. `AIChunk.vectorize_point_id` maps chunk→point (db/models.py:186), and job status/`embedding_status == "completed"` shows the terminal state (V2 `get_job_status`, routes.py:277-282), but nothing lists/queries Vectorize points by document to confirm per-chunk indexing. The closest evidence is `job status == "completed"` + `embedding_status == "completed"` + `_assert_upsert_confirmed` having passed — but that confirms the upsert call was accepted, not that each chunk is individually queryable. NOT VERIFIED (no such mechanism exists in code).

---

## 6. Deletion lifecycle

1. **Django** `DELETE /api/ai/documents/{backend_thesis_id}/` (`AIDocumentDeleteView`): checks write access (owner/admin), forwards to V2 `DELETE /api/v2/documents/{backend_thesis_id}`, returns 200 `{"detail": ...}`.
2. **V2** `IngestionService.delete_document` (service.py:664-719): access check (owner/admin); collects `vectorize_point_id`s (`_collect_point_ids`, service.py:269-276); deletes source file; deletes `AIDocument` (cascades pages/chunks/jobs); calls `_delete_vectors(point_ids)` (service.py:278-292) → `VectorizeService.adelete` → Cloudflare `/delete_by_ids`.
3. **Failure handling:** Vectorize delete failures are caught and logged as warnings; they do **not** propagate and do **not** change the HTTP 200. DB deletion happens first, so orphaned Vectorize points are possible but retrieval re-resolves chunks against the DB and drops unresolved ones (`resolve_authorized_chunks`, retrieval/service.py:361-362).

**Verification:** CODE VERIFIED. UNIT TEST VERIFIED — `test_ingestion_reliability.py:308`, vectorize adelete tests (lines 343/358/370).

**Resolution of uncertainty E:** Document deletion **does** invoke Vectorize deletion (`_delete_vectors` → `adelete`), but it is **best-effort**; failures are logged, not returned. HTTP 200 is **not** proof of completed Vectorize deletion.

---

## 7. Test prerequisites (for a safe Stage 3.5.5 test)

To run any live test of these contracts, the following must be true (none verified live):

- **Django backend running** on `http://127.0.0.1:8000` (`config/settings.py:59`), PostgreSQL available (`DATABASES`, settings.py:125-134), migrations applied.
- **V2 AI service running** at `AI_SERVICE_URL` (settings.py:207) with `BACKEND_API_INTERNAL_TOKEN` configured on both sides (settings.py:209; `ingestion/services.py:48-56` raises if missing).
- **A registered + active user** (POST /api/auth/register/, then login for JWT). `IsActiveUser` requires `status == "active"` (`accounts/permissions.py:21-27`).
- **A Django Thesis record** owned by that user (POST /api/theses/ with a PDF file) — `backend_thesis_id` must exist (`derive_access_level`, services.py:132-135).
- **Vectorize configured** (`VECTORIZE_API_TOKEN`, `VECTORIZE_ACCOUNT_ID`) for full indexing; otherwise ingestion fails at `vectorize_not_configured` (service.py:587-595) and similarity degrades to lexical-only.
- **Embedding model available** (`sentence-transformers`, `BAAI/bge-large-en-v1.5`) — `EmbeddingService` raises `ConfigurationError` if not installed (`embeddings/service.py:45-63`); ingestion then fails at the embedding stage.
- **DeepSeek configured** for RAG (`llm/router.py`) — RAG returns 503 `provider_unavailable` if DeepSeek fails (no Groq fallback, rag/service.py:528-539).
- **A valid two-page PDF with extractable text** (see §8.H) — blank/scanned PDFs fail ingestion (`no_extractable_text`, service.py:368-377).

---

## 8. Unresolved questions

### A. backend_thesis_id must be an existing Django Thesis PK? — RESOLVED (CODE VERIFIED)
Yes, enforced at the API/permission layer: `derive_access_level` and `check_thesis_write_access` both call `Thesis.objects.get(id=thesis_id)` and return None/False when missing → 403 (`ingestion/services.py:132-135`, `111-114`). Caveat: there is **no DB-level foreign key** from V2 `ai_documents.backend_thesis_id` to Django `theses_thesis.id`; it is a String unique field. Enforcement is contractual, not referential.

### B. How Django derives backend_user_id and access level? — RESOLVED (CODE VERIFIED)
`backend_user_id = str(request.user.id)` from the JWT-authenticated user (`ai_integration/views.py:142`). Access level is **never** client-chosen: `access_level = derive_access_level(thesis_id, request.user)` (`views.py:127`, `services.py:123-149`), derived from the Thesis record; non-published theses are forced to `"private"`. The frontend confirms it does not send these fields (`aiService.ts:57`).

### C. Frontend upload request is /api/ai/documents/upload/? — RESOLVED (CODE VERIFIED)
Yes: `frontend/src/services/aiService.ts:58` calls `request('ai/documents/upload/', ...)` against base `http://127.0.0.1:8000/api` (`lib/api.ts:9`). Full URL: `POST http://127.0.0.1:8000/api/ai/documents/upload/`.

### D. Exact ID expected by document deletion? — RESOLVED (CODE VERIFIED)
`backend_thesis_id` (the Django Thesis PK), as the URL path parameter (`ai_integration/views.py:213`, `urls.py:51-55`). V2 `delete_document` looks up `AIDocument` by `backend_thesis_id` (`ingestion/service.py:675-680`). **Not** the internal `AIDocument.id` UUID.

### E. Does deletion invoke Vectorize deletion and how are failures handled? — RESOLVED (CODE VERIFIED, UNIT TEST VERIFIED)
Yes, best-effort, inside `delete_document` (`ingestion/service.py:701-713`) via `_delete_vectors` (`service.py:278-292`) → `VectorizeService.adelete` → Cloudflare `/delete_by_ids` (`embeddings/vectorize.py:151-184`). Failures are caught and logged, not raised. HTTP 200 ≠ proof of Vectorize deletion.

### F. Are similarity search and normal research retrieval separate? — RESOLVED (CODE VERIFIED)
Yes. Separate endpoints (`/api/ai/similarity/check/` vs `/api/ai/rag/ask/`), separate V2 services (`SimilarityService` vs `RAGService`), separate algorithms (lexical shingle ± semantic vs hybrid Vectorize+FTS+RRF+DeepSeek generation).

### G. Reliable way to verify a document's chunks were indexed? — RESOLVED: NO SUCH MECHANISM
No endpoint lists or queries Vectorize points by document. `AIChunk.vectorize_point_id` (db/models.py:186) and `embedding_status`/`job status` (routes.py:277-282) show terminal state but not per-chunk presence in Vectorize. `_assert_upsert_confirmed` confirms the upsert call was accepted (service.py:294-314). NOT VERIFIED — no per-document verification endpoint exists.

### H. Correct way to create a valid two-page test PDF with pypdf? — RESOLVED (CODE VERIFIED reasoning; NOT runtime-verified)
- **Structure:** Use `pypdf.PdfWriter()` (public constructor), `writer.add_blank_page(width, height)` twice (public method), then `writer.write(file_obj)` (public method). pypdf itself builds the cross-reference table and trailer — no handcrafted xref offsets or stream lengths, no private writer internals.
- **Critical caveat:** `add_blank_page()` yields pages with **no extractable text**. `extract_pdf_pages` flags them scanned (`text=None`, `document_processing/extraction.py:53-55`) and ingestion rejects the document with `no_extractable_text` (`ingestion/service.py:368-377`). So a blank two-page PDF is structurally valid but **cannot pass ingestion**.
- **For extractable text:** pypdf exposes **no public text-drawing API** (`draw_string`/`show_text` equivalent). Producing text requires raw content-stream manipulation (private internals, discouraged) or a dedicated generator such as **reportlab**, then validating/reading with `pypdf.PdfReader` + `extract_text()`. The correct test-PDF approach: generate a two-page text PDF with reportlab (or equivalent), verify page count and extractable text via `pypdf.PdfReader`, then upload. Runtime behavior of this approach is NOT VERIFIED (not executed).

---

## 9. Proposed safe test sequence (do not execute yet)

This is a **read-only proposal** for review. It creates no users/documents and performs no destructive operations until approved.

1. Register a user (POST /api/auth/register/) → capture JWT `access`.
2. Login → confirm JWT pair.
3. Create a thesis (POST /api/theses/) with `status=published, access_policy=public` and a valid two-page text PDF → capture `thesis.id` (= `backend_thesis_id`).
4. Upload PDF (POST /api/ai/documents/upload/, multipart `file` + `backend_thesis_id`) → capture `document_id`, `job_id`.
5. Poll job status (GET /api/ai/documents/jobs/{job_id}/) until `status == completed`; confirm `result.embedding_status == completed`.
6. Retrieve extracted text (GET /api/ai/documents/{document_id}/text/) → confirm 2 pages.
7. Similarity check (POST /api/ai/similarity/check/ with text from the PDF) → confirm matches.
8. RAG (POST /api/ai/rag/ask/ with a question) → confirm answer + citations.
9. Document deletion (DELETE /api/ai/documents/{backend_thesis_id}/) → confirm 200; then confirm GET job status / text returns 404 and `AIDocument` row is gone (DB-level confirmation only, via a read query — no Vectorize side-channel assertion because deletion is best-effort).
10. Confirm no leftover: attempt re-upload for same `backend_thesis_id` → expect either `document_already_exists` (if not failed) or a clean retry path.

**Cleanup:** Since no test user/document should be left behind, deletion in step 9 is the cleanup; do not create additional users/theses beyond the single test thesis. All steps require the live Django + V2 services to be running, which is not the case in this audit session.

---

## Summary of verification levels

| Area | Code | Unit test | Live |
|---|---|---|---|
| Registration/login | VERIFIED | — | — |
| Thesis creation | VERIFIED | — | — |
| PDF upload contract | VERIFIED | VERIFIED (backend tests_p2) | — |
| Job status | VERIFIED | VERIFIED | — |
| Extracted text | VERIFIED | — | — |
| Similarity search | VERIFIED | VERIFIED (route wiring) | — |
| RAG retrieval | VERIFIED | VERIFIED (security/hybrid) | — |
| Document deletion | VERIFIED | VERIFIED (reliability) | — |
| Vectorize deletion | VERIFIED | VERIFIED (adelete unit tests) | — |
| Per-chunk indexing verification | NOT VERIFIED (no endpoint) | — | — |
| Two-page pypdf test PDF | VERIFIED (reasoning) | — | NOT VERIFIED |

---

**Prepared by:** independent engineering review, 2026-11-05. **Repository:** `C:\Users\Administrator\Desktop\AI_Intelligence_baseline_scaffold`. **No production code was modified. Stopping after audit per instructions.**