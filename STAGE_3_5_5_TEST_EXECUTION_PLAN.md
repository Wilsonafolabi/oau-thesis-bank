# OAU THESIS BANK — STAGE 3.5.5 TEST EXECUTION PLAN (AMENDED)

**Status:** Plan only. Conditioned on the reviewer's amendments (2026-11-05). No implementation. No execution. No live tests run. Nothing here is live-verified.
**Source of truth:** `STAGE_3_5_5_INDEPENDENT_CONTRACT_AUDIT.md` + this amended plan. Both derived from source inspection, not runtime.
**Restrictions honored:** No production code modified. No test users/documents created. No live tests executed. No credentials/JWTs/secrets printed. No invented endpoint contracts. Stage 3.6 not started.

---

## 0. Amendments applied (reviewer directives)

| # | Directive | Disposition |
|---|-----------|-------------|
| 1 | Separate public retrieval and private access tests | Done: §2 has two distinct fixtures/sequences |
| 2 | Correct cleanup order (V2 doc → verify V2 DB → Django thesis → verify storage) | Done: §5 exact 4-step sequence |
| 3 | Correct duplicate-guard test (before cleanup, expect 409) | Done: §4.3; source confirms 409 path while document exists |
| 4 | Resolve R2 deletion implementation | Done: §6 — V2 `object_key` cleanup is local `Path.unlink`, NOT R2 client |
| 5 | Avoid permanent account proliferation | Done: §2.1 — dedicated reusable accounts, env-var credentials |
| 6 | Record cross-encoder runtime status | Done: §4.6 — record degraded vs. verified |

---

## 1. Confirmed ID semantics (CODE VERIFIED)

| Identifier | Type | Django/V2 | Source | Role in test |
|---|---|---|---|---|
| `User.id` | BigAutoField (int) | Django `accounts.User` | `backend/accounts/models.py:57` (`USERNAME_FIELD=email`) | JWT subject |
| `Thesis.id` | BigAutoField (int) | Django `theses.Thesis` | `backend/theses/models.py:37-39` | Passed as `backend_thesis_id` |
| `AIDocument.id` | UUID | V2 `ai_documents.id` | `src/oau_ai/db/models.py:58-62` | Returned on upload as `document_id` |
| `AIJob.id` | UUID | V2 `ai_jobs.id` | `src/oau_ai/db/models.py:206-210` | Returned on upload as `job_id` |
| `AIChunk.vectorize_point_id` | UUID string | V2 `ai_chunks` | `src/oau_ai/db/models.py:186` | Set at `ingestion/service.py:601` |

**Critical:** `backend_thesis_id` is the **Django Thesis PK** (int, sent as string). `document_id` in the text endpoint is the **V2 AIDocument UUID**. The delete endpoint path param is `backend_thesis_id` (Django PK), confirmed by `check_thesis_write_access` → `Thesis.objects.get(id=thesis_id)` (`backend/ai_integration/services.py:105-120`) and V2 `delete_document` lookup by `backend_thesis_id` (`ingestion/service.py:675-680`).

---

## 2. Test fixture design

### 2.1 Dedicated reusable test accounts (avoids proliferation)

**Constraint:** Do not create unlimited UUID-suffixed accounts per run. Use fixed dedicated accounts and reuse them across runs. Credentials live in environment variables only; never printed.

| Account | Purpose | Env var for email | Env var for password |
|---|---|---|---|
| User A (owner/uploader) | Public + private thesis owner | `STAGE355_USER_A_EMAIL` | `STAGE355_USER_A_PASSWORD` |
| User B (viewer, no access) | Access-denial actor | `STAGE355_USER_B_EMAIL` | `STAGE355_USER_B_PASSWORD` |

**Registration (idempotent):** Before the test, attempt `POST /api/auth/register/` for each account. If `400 {"detail": "A user with this email already exists."}`, treat the account as pre-existing and proceed to login. Do not print JWTs. Capture `access` token in memory only.

- **Source:** `backend/accounts/views.py:26-44` (`RegisterView`), `serializers.py:18-49` (`RegisterSerializer` — `role` must not be `"admin"`, `password` min 8).
- **Login:** `POST /api/auth/login/` (TokenObtainPairView, `backend/accounts/urls.py:14`).
- **Active status:** `User.status` defaults to `active` (`models.py:55`); `IsActiveUser` requires `status == "active"` (`backend/accounts/permissions.py:21-27`).

### 2.2 Public thesis fixture (User A)

- **Endpoint:** `POST /api/theses/`
- **Source:** `backend/theses/views.py:53-122`, `serializers.py:32-121`, `urls.py:6-7`
- **Auth:** JWT `Authorization: Bearer <access>` (User A); `IsAuthenticatedOrReadOnly, IsActiveUser`
- **Body:** multipart/form-data. Fields: `title, author, department, faculty, year, abstract, supervisor, tags, status=published, access_policy=public, file=<PDF>`
- **File:** PDF only, ≤10 MB (`validate_file`, `serializers.py:97-102`); `file` is write_only (`serializers.py:68`)
- **Owner:** auto-set to User A (`serializers.py:106`)
- **Resulting access_level:** published + public → `derive_access_level` returns `"public"` (`services.py:142-149`)
- **Capture:** `thesis.id` → used as `backend_thesis_id` in upload.

### 2.3 Private thesis fixture (User A)

- **Endpoint:** `POST /api/theses/` (same contract as 2.2)
- **Body:** same, but `access_policy=private`, `status=published`
- **Resulting access_level:** published + private → `derive_access_level` returns `"private"` (`services.py:142-149`)
- **Capture:** `thesis.id` → used as `backend_thesis_id` in upload.

> Note: `derive_access_level` forces non-published theses to `"private"` (`services.py:142-143`). Using `published + private` makes the intent explicit.

### 2.4 Test PDF generation (ReportLab, validated with pypdf)

**Constraint:** pypdf has no public text-drawing API (`document_processing/extraction.py` only reads via `PdfReader` + `extract_text()`). A blank `add_blank_page` PDF yields `text=None`/scanned pages and ingestion fails with `no_extractable_text` (`ingestion/service.py:368-377`).

**Approach (NOT runtime-verified):**
1. Generate a two-page PDF with ReportLab `canvas.Canvas`, drawing a unique searchable passage on each page, e.g. `OAU_STAGE355_<uuid4>_PAGE_1` and `OAU_STAGE355_<uuid4>_PAGE_2`.
2. **Pre-upload validation:** Open the bytes with `pypdf.PdfReader`; assert `len(reader.pages) == 2`; assert each `page.extract_text()` is non-None, non-empty, and contains the expected passage marker. This guarantees the PDF is not scanned/blank.
3. Upload the validated bytes.

**Why:** Ingestion extraction flags `text is None or not text.strip()` as `is_scanned=True, text=None` (`extraction.py:53-55`); a document with zero extractable pages fails (`ingestion/service.py:368-377`).

### 2.5 Authentication without exposing JWTs

- Obtain `access` token from register/login response (in-memory variable only).
- Attach `Authorization: Bearer <access>` to every authenticated request.
- **Never print, log, or assert-print the token.** (The previous script's defect of printing part of a JWT is explicitly avoided.)
- Token lifetime: 1 hour (`backend/config/settings.py:194-196`).

---

## 3. Corrected test sequences

### 3.1 Sequence A — Public ingestion + RAG retrieval (User A)

| Step | Action | Endpoint | Method | Expected |
|---|---|---|---|---|
| A1 | Login as User A | `/api/auth/login/` | POST | `{access, refresh}` |
| A2 | Create public thesis | `/api/theses/` | POST | 201; capture `thesis.id` (public) |
| A3 | Upload PDF | `/api/ai/documents/upload/` | POST (multipart: `file`, `backend_thesis_id`) | 202; capture `document_id`, `job_id` |
| A4 | Poll job status | `/api/ai/documents/jobs/{job_id}/` | GET | `status == completed`, `result.embedding_status == completed` |
| A5 | Retrieve extracted text | `/api/ai/documents/{document_id}/text/` | GET | `total_pages == 2`, page text contains passage |
| A6 | RAG query | `/api/ai/rag/ask/` | POST (`question` = passage) | ≥1 citation with `backend_thesis_id == thesis.id`, `text_snippet` matches passage |
| A7 | Similarity check | `/api/ai/similarity/check/` | POST (`text` = passage) | ≥1 match with `backend_thesis_id == thesis.id` |

**Source confirmations:**
- A3: `backend/ai_integration/views.py:95-167`, `urls.py:35`; client does NOT send `backend_user_id`/`access_level` (derived server-side, `views.py:127,142`; `services.py:123-149`).
- A4: `backend/ai_integration/views.py:170-202`; V2 `"success"` aliased to `"completed"` (`views.py:37,196-199`).
- A5: `backend/ai_integration/views.py:246-275`; path param is V2 `document_id` UUID.
- A6: `backend/ai_integration/views.py:309-374`; V2 `RAGService.ask` — hybrid retrieval + DeepSeek + citation validation (`rag/service.py:227-384`). **Infrastructure caveat:** if DeepSeek unavailable → 503 `provider_unavailable`, no Groq fallback (`rag/service.py:528-539`).
- A7: `backend/ai_integration/views.py:532-570`; lexical shingle ± optional semantic (degraded to lexical if Vectorize unconfigured, `similarity/service.py:298-310`).

### 3.2 Sequence B — Private access-denial (User A owner, User B denied)

| Step | Action | Endpoint | Method | Expected |
|---|---|---|---|---|
| B1 | Login as User A | `/api/auth/login/` | POST | `{access, refresh}` |
| B2 | Create private thesis | `/api/theses/` | POST (`access_policy=private`) | 201; capture `thesis.id` (private) |
| B3 | Upload PDF | `/api/ai/documents/upload/` | POST | 202; capture `document_id`, `job_id` |
| B4 | Poll job status | `/api/ai/documents/jobs/{job_id}/` | GET | `status == completed` |
| B5 | User B accesses private text | `/api/ai/documents/{document_id}/text/` | GET (User B JWT) | **403 Forbidden** |
| B6 | User B RAGs private thesis | `/api/ai/rag/ask/` | POST (User B JWT, `document_ids=[document_id]`) | **403 Forbidden** |

**Source confirmations:**
- B5: V2 `get_document_text` checks `document.backend_user_id != actor.user_id and "admin" not in actor.roles` → 403 (`routes.py:443-447`). Django `AIDocumentDeleteView`-style ownership enforced in `IngestionService` (`ingestion/service.py:346-356`, `650-660`, `689-699`).
- B6: `AIRAGAskView` enforces `check_thesis_access(doc_id, request.user)` per `document_id` (`views.py:340-347`); V2 `verify_access_before_retrieval` (`retrieval/service.py:410-442`).
- **Public contrast:** Per reviewer directive, do NOT expect 403 for a public document in RAG/similarity: `_build_access_conditions` includes `access_level == "public"` for any actor (`retrieval/service.py:111-124`). (The text endpoint itself is owner-or-admin regardless, but Sequence A only asserts User A access.)

### 3.3 Sequence C — Duplicate-guard (before cleanup)

| Step | Action | Endpoint | Method | Expected |
|---|---|---|---|---|
| C1 | (After A4, document completed) Attempt second upload | `/api/ai/documents/upload/` | POST (same `file`, same `backend_thesis_id`) | **409 Conflict** (`document_already_exists`) |

**Source:** `ingestion/service.py:107-116` — if `AIDocument` exists and latest job is not `FAILED`, raise `document_already_exists` → mapped to HTTP 409 by `_map_v2_error` (`views.py:52-53`). After deletion (Sequence D), the `AIDocument` row is gone (`ingestion/service.py:710-711`), so the duplicate guard would NOT fire — hence this test MUST run before cleanup.

> If the reviewer prefers, Sequence C can be omitted; it is optional. Source confirms 409 is the correct behavior while the document exists.

---

## 4. RAG cross-encoder runtime status (amendment 6)

During Sequence A step A6, record the following (observed, not assumed):

- `Reranker.available` property (`rag/service.py:118-122`): True if `sentence-transformers` `CrossEncoder` loaded.
- If `available == True`: reranking executed (`rag/service.py:299-302`, `Reranker.rerank` lines 153-201).
- If `available == False`: reranking skipped, chunks returned in original order with log warning (`rag/service.py:173-179`). Report reranking as **degraded**, not verified.
- `sentence-transformers` import failure path: `rag/service.py:138-143`.

**Record in test output:** `cross_encoder_available: <bool>`, `reranking_degraded: <bool>`. Do not hardcode.

---

## 5. Exact corrected cleanup sequence (amendment 2)

For **each** test document (public and private theses), in this order:

1. **Delete V2 document:** `DELETE /api/ai/documents/{backend_thesis_id}/` (User A JWT). Path param = Django Thesis PK.
   - Source: `backend/ai_integration/views.py:205-243`, `urls.py:51-55`; V2 `delete_document` (`ingestion/service.py:664-719`).
   - Expected: 200 `{"detail": "Document <id> deleted."}`.
2. **Verify V2 DB records removed:**
   - `GET /api/ai/documents/jobs/{job_id}/` → 404 (`job_not_found`, `ingestion/service.py:632-639`).
   - `GET /api/ai/documents/{document_id}/text/` → 404 (`Document not found`, `routes.py:439-440`).
   - Optionally: direct DB read confirms `ai_documents` row for `backend_thesis_id` is gone (cascades to `ai_pages`, `ai_chunks`, `ai_jobs` via SQLAlchemy cascade / ON DELETE CASCADE, `db/models.py:86-105,119-145,164-171,206-219`).
3. **Delete Django Thesis record:** `DELETE /api/theses/{id}/` (User A JWT; owner or admin).
   - Source: `backend/theses/views.py:115-122` (`ThesisViewSet.destroy`).
   - Expected: 204 (DRF ModelViewSet destroy default).
4. **Verify Django storage cleanup:** Confirm the thesis file object is no longer accessible/stale.
   - **Limitation recorded (§6):** V2 `object_key` cleanup is local `Path(document.object_key).unlink` (`ingestion/service.py:705-707`), NOT the R2/S3 client. Django `Thesis.file` cleanup depends on `STORAGES` default backend (`config/storage.py:49-63`: local `FileSystemStorage` or S3/R2 `S3Storage`). The test must not claim R2 deletion unless `STORAGE_PROVIDER=r2` is confirmed and Django storage deletion is observed.

**Ordering rationale:** The Django Thesis must remain available while V2 deletion authorization runs (`check_thesis_write_access` looks up `Thesis.objects.get(id=thesis_id)`, `services.py:111-112`). Deleting the Django Thesis first would break V2 deletion authorization.

---

## 6. R2 deletion implementation resolution (amendment 4)

**Finding (CODE VERIFIED):**

- V2 stores files under `storage_base_path` (`os.getenv("STORAGE_BASE_PATH", "./storage/documents")`, `ingestion/service.py:66-69`).
- `AIDocument.object_key` = `str(saved_path)` where `saved_path = storage_dir / f"{document_id}.pdf"` (`ingestion/service.py:143`).
- V2 deletion: `file_path = Path(document.object_key); file_path.unlink(missing_ok=True)` (`ingestion/service.py:705-707`).
- **This is local filesystem deletion only.** V2 does **not** instantiate the Django `storages` S3/R2 client for its `object_key`.

- R2/S3 is configured solely in Django's `STORAGES` default backend (`config/storage.py:49-63`): `storages.backends.s3.S3Storage` when `STORAGE_PROVIDER in {minio, r2}`, else `FileSystemStorage`. This governs Django `Thesis.file` (`backend/theses/models.py:50-55`), not V2's `object_key`.

**Recorded limitation:** The test must **not** claim the R2 object is deleted by V2 document deletion. V2 deletion removes a local file at `object_key`. Django Thesis deletion (`step 4` of cleanup) relies on Django's storage backend; whether that is R2 depends on `STORAGE_PROVIDER` env, which is not verified in this plan. Record `storage_provider: <env value>` and `r2_object_deleted: <not asserted>`.

---

## 7. Account proliferation avoidance (amendment 5)

- Use exactly two dedicated accounts (User A, User B) with fixed emails from `STAGE355_USER_*_EMAIL` / `STAGE355_USER_*_PASSWORD` env vars.
- Reuse across runs; do not generate UUID-suffixed emails per run.
- Idempotent registration: tolerate "already exists" 400 and proceed to login.
- Credentials never printed or logged.

---

## 8. Endpoint contract summary (unchanged, clarified)

| # | Django endpoint | Method | Auth | Key request fields | Key response fields | Source |
|---|---|---|---|---|---|---|
| 1 | `/api/auth/register/` | POST | AllowAny | email, password, name, role(!=admin), department, faculty | user, access, refresh | `accounts/views.py:26-44` |
| 2 | `/api/auth/login/` | POST | AllowAny | email, password | access, refresh | `accounts/urls.py:14` |
| 3 | `/api/theses/` | POST | IsAuthenticated+Active | multipart: title, file, status, access_policy, ... | Thesis data (incl. id) | `theses/views.py:53-122`, `serializers.py:32-121` |
| 4 | `/api/ai/documents/upload/` | POST | IsAuthenticated+Active | multipart: file, backend_thesis_id, thesis_metadata | document_id, job_id, status, message | `ai_integration/views.py:95-167` |
| 5 | `/api/ai/documents/jobs/{job_id}/` | GET | IsAuthenticated+Active (owner/admin) | path job_id | job_id, status, stage, result, error_* | `ai_integration/views.py:170-202` |
| 6 | `/api/ai/documents/{document_id}/text/` | GET | IsAuthenticated+Active (owner/admin) | path document_id (V2 UUID) | document_id, backend_thesis_id, pages[], total_pages | `ai_integration/views.py:246-275` |
| 7 | `/api/ai/similarity/check/` | POST | IsAuthenticated+Active | JSON: text, min_score, max_matches, ... | matches[], exact_matches[], semantic_matches[] | `ai_integration/views.py:532-570` |
| 8 | `/api/ai/rag/ask/` | POST | IsAuthenticated+Active | JSON: question, document_ids?, top_k | answer, citations[], confidence, insufficient_evidence | `ai_integration/views.py:309-374` |
| 9 | `/api/ai/documents/{backend_thesis_id}/` | DELETE | IsAuthenticated+Active (owner/admin) | path backend_thesis_id (Django PK) | detail | `ai_integration/views.py:205-243` |

---

## 9. Expected evidence (pass criteria)

| Check | Expected | Source |
|---|---|---|
| Register/login | `{access, refresh}` present (not printed) | `views.py:37-44` |
| Thesis create | `id` present = `backend_thesis_id` | `serializers.py:109` |
| Upload (public & private) | 202; `document_id` (UUID), `job_id` (UUID) | `routes.py:213-218` |
| Job completed | `status == completed`, `result.embedding_status == completed` | `views.py:37,196-199`; `routes.py:277-282` |
| Text retrieval | `total_pages == 2`, page text contains passage | `routes.py:464-479` |
| RAG citation (public) | ≥1 citation `backend_thesis_id == thesis.id`, snippet matches passage | `rag/service.py:560-620` |
| Similarity match (public) | ≥1 match `backend_thesis_id == thesis.id` | `similarity/service.py:264-281` |
| Private text denial (User B) | 403 | `routes.py:443-447` |
| Private RAG denial (User B) | 403 | `views.py:340-347`; `retrieval/service.py:410-442` |
| Duplicate guard | 409 `document_already_exists` | `ingestion/service.py:107-116`; `views.py:52-53` |
| Deletion | 200 `{"detail": ...}`; then job/text 404 | `routes.py:330`; `ingestion/service.py:632-639` |
| Cross-encoder status | `cross_encoder_available` bool recorded; degraded if False | `rag/service.py:118-122, 173-179` |

---

## 10. Unresolved limitations (recorded, not worked around)

1. **No per-chunk Vectorize verification endpoint.** Cannot confirm searchable presence of individual chunks via API. Strongest evidence: RAG/similarity citations (§9).
2. **HTTP 200 on deletion ≠ Vectorize removal.** Vectorize delete is best-effort, logged-not-raised (`ingestion/service.py:289-292`).
3. **DeepSeek dependency for RAG.** If unavailable → 503 `provider_unavailable`, no Groq fallback (`rag/service.py:528-539`). Treat as infra precondition.
4. **Cross-encoder may be unavailable.** If `sentence-transformers`/`CrossEncoder` missing, reranking skipped with log warning — report degraded (§4).
5. **BM25 not implemented.** Only PostgreSQL Boolean FTS + RRF (audit §4.4). Do not expect BM25 scores.
6. **V2 object-key cleanup is local, not R2.** `Path(object_key).unlink` only (`ingestion/service.py:705-707`). R2 deletion unconfirmed (§6).
7. **No user-delete endpoint.** Test users persist; reuse dedicated accounts (§7).
8. **Blank/two-page pypdf PDF fails ingestion.** Must use ReportLab text PDF validated with `pypdf.PdfReader` (§2.4).

---

## 11. Proceed-to-implementation gate

This amended plan must be reviewed and approved before:
- Writing the integration test file.
- Creating any test user or document (via live API).
- Executing any live request.
- Proceeding to Stage 3.6.

**Prepared from source inspection only (2026-11-05). No live verification claimed.**