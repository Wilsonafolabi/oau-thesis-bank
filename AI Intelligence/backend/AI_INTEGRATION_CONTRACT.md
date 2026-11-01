# AI Integration Contract (Django ⇄ V2 ⇄ Frontend)

Scope: the AI endpoints the React frontend actually calls, the exact payloads
Django accepts and returns, and the mismatches found during P2.

Django is the public API. It authenticates the user, derives identity and
authorization scope, and forwards to the V2 service with service-to-service
auth. V2 paths are internal and are not a frontend contract.

---

## 1. RAG question

`POST /api/ai/rag/ask/` (JWT required)

Request:

```json
{
  "question": "string (required)",
  "document_ids": ["123", "456"],
  "top_k": 5
}
```

`document_ids` are Django thesis IDs. Every ID is access-checked before the
request is forwarded; a single inaccessible ID rejects the whole request with
`403`. When omitted, retrieval runs across everything the actor may see.

Response `200`:

```json
{
  "answer": "string",
  "citations": [Citation],
  "confidence": 0.0,
  "decision_engine": "string (internal — never rendered in UI)",
  "llm_tier": 1,
  "trace_id": "uuid",
  "request_id": "uuid",
  "insufficient_evidence": false,
  "message": null,
  "abstention_reason": null
}
```

`abstention_reason` is one of `null`, `no_evidence`, `weak_evidence`,
`retrieval_degraded`, `blocked_by_safety`. It exists so callers can distinguish
"nothing was found" from "the index was unavailable" without parsing prose.

### Citation object

```json
{
  "chunk_id": "uuid",
  "document_id": "uuid",
  "backend_thesis_id": "123",
  "text_snippet": "first 200 chars of the chunk",
  "page_number": 4,
  "section": null,
  "relevance_score": 0.032
}
```

`relevance_score` is the fused retrieval score of that chunk, not a
model-reported confidence. A citation is only emitted when the `[Source N]`
marker indexes a chunk that was retrieved for that request and the sentence
carrying the marker shares content words with that chunk. This proves the
source exists and was retrieved; it does not certify the claim is true.

### Insufficient evidence

Abstention is signalled by `insufficient_evidence: true` with `200`, not by an
error status. `answer` is `""` and `citations` is `[]` when no evidence was
available at all.

`[Memory: key]` — durable researcher context, ranked by relevance, confidence
and recency, de-duplicated, and truncated to `MAX_MEMORY_CONTEXT_CHARS`
(1500). Working-memory exchanges are a separate, shorter-lived budget
(4000 chars, last 5 verbatim). Memory is injected as *context only*: the system
prompt states it is not thesis evidence and it can never override the user's
current instruction.

---

## 2. Thesis summaries

`POST /api/ai/memory/thesis-summaries/` (JWT required)

Two modes on the same endpoint:

```json
{"backend_thesis_id": "123", "generate": true}
```

`generate: true` summarises the thesis from its own extracted chunks. Every
content field in the request is ignored. Otherwise the supplied structure is
stored, but only after the thesis access check passes (`403` on denial).

Response `200`:

```json
{
  "document_id": "uuid",
  "backend_thesis_id": "123",
  "user_id": "5",
  "title": "string | null",
  "abstract_summary": "Research problem: ...\n\nDataset / study population: ...",
  "research_questions": ["..."],
  "objectives": ["..."],
  "methodology": "string | null",
  "findings": ["finding", "Contribution: ..."],
  "limitations": ["limitation", "Future work: ..."],
  "key_entities": ["..."],
  "confidence": 0.67,
  "missing_sections": ["dataset", "future_work"]
}
```

`GET /api/ai/memory/thesis-summaries/{backend_thesis_id}/` returns the same
shape for the caller's own summary (`404` if none).

Field mapping is constrained by the existing schema: `contributions` are stored
as `findings` entries prefixed `Contribution:`, and `future_work` as
`limitations` entries prefixed `Future work:`. The prefixes are how the two are
recovered on read, which is why they are preserved verbatim.

`confidence` is the fraction of the nine sections the source text actually
supported — a deterministic coverage figure, not a model-reported score.
`missing_sections` lists what the thesis did not state. Nothing is invented to
fill a gap, and a provider failure returns `503` with no summary written.

---

## 3. Document upload

`POST /api/ai/documents/upload/` (multipart, JWT required)

Form fields: `file` (PDF), `backend_thesis_id`, optional `thesis_metadata`.

`backend_user_id` and `access_level` are **ignored if supplied** — both are
derived server-side. The access level comes from the thesis:

| Thesis state | Stored access level |
|---|---|
| not `published` | `private` |
| `published` + `public` | `public` |
| `published` + `restricted` | `restricted` |
| `published` + `private` | `private` |

Response `202`:

```json
{"document_id": "uuid", "job_id": "uuid", "status": "pending", "message": "..."}
```

Errors: `400` validation, `403` not owner/admin, `409` already ingested,
`502` upstream failure, `503` AI service unavailable.

---

## 4. Job status

`GET /api/ai/documents/jobs/{job_id}/` (JWT required)

```json
{
  "job_id": "uuid",
  "status": "pending | processing | completed | failed",
  "stage": "extraction | chunking | embedding | vectorize | complete | failed",
  "message": "string",
  "result": {"document_id": "...", "backend_thesis_id": "...", "embedding_status": "completed"},
  "error_message": null,
  "error_stage": null,
  "attempts": 1,
  "max_attempts": 3
}
```

The AI service stores the terminal success state as `success`; Django maps it
to `completed` because that is the published vocabulary the frontend polls on.
`failed` carries `error_message` and `error_stage` (the stage that failed).

Only the document owner or an admin may read a job. Denial is `403`; a missing
job is `404`.

---

## 5. Error body

All mapped errors share one shape:

```json
{"error": "AI Service Error", "detail": "human readable", "code": "machine_code"}
```

`code` is present only when the AI service supplied one (`access_denied`,
`document_already_exists`, `document_not_found`, `vectorize_not_configured`, …).
Private document existence is never revealed: an inaccessible document and a
missing document both surface as denial/missing without distinguishing which.

---

## 6. Mismatches found (P2 fixes vs. deferred P6 work)

Fixed in P2 (backend):

- **Job status vocabulary.** V2 returned `success`; the frontend polls for
  `completed`. Django now normalises it, so polling terminates.
- **Client-chosen `access_level`.** The upload endpoint accepted the caller's
  value, so a draft thesis could be indexed as `public` and become globally
  retrievable. Now derived from the thesis.
- **Upstream errors flattened to `502`.** `409`/`403`/`404`/`503` are now
  produced from the upstream status and error code.

Deferred to P6 (frontend must change — not done in P2):

1. `RagResponse.sources?: CitationSource[]` is declared and may be rendered,
   but the backend only returns `citations`. `CitationSource.similarity` has no
   backend equivalent and must not be fabricated — render `citations`, or drop
   the field.
2. `abstention_reason` is new and untyped on the client; the UI should show
   `retrieval_degraded` differently from `no_evidence`.
3. `getResearchNetwork()` calls `ai/intelligence/researchers`, which has **no
   Django route** → `404`. Either implement a real route or remove the call.
4. `getWorkingMemory()` calls `ai/memory/working/`, which has **no route** and
   falls through to `memory/<memory_id>/` with `memory_id="working"`.
5. `ingestThesisPdf` still sends `access_level` in `ThesisIngestionMetadata`;
   it is ignored, so the field is misleading and should be removed.
6. `checkSimilarityPdf`, `checkSimilarityText` and `detectAIWriting` call
   `:8888/api/v1/...` directly. The V2 service only implements `/api/v2/...`;
   those endpoints do not exist (P5 scope), so these screens cannot work today.
7. `askGeneralAssistant` sends `provider: "deepseek" | "groq"` from the client.
   Provider names must not reach the UI; the selector should be a neutral
   "Model 1 / Model 2" that the backend maps.

---

## 7. Authorization rules (enforced in V2, authoritative in PostgreSQL)

A chunk is returned only when its document row still exists **and** the actor
satisfies: `access_level == "public"` OR `backend_user_id == actor.user_id` OR
the actor holds `admin`.

Vectorize metadata is a hint only. Every dense candidate is re-resolved against
the database, and unresolvable candidates (deleted chunk, deleted document,
denied access, malformed metadata) are dropped before reranking or generation.
An approved-access collaborator is **not** represented in the V2 index; the
Django access-request flow grants read access to the thesis record, not to AI
retrieval. Supporting that requires syncing collaborator IDs into document
metadata — out of P2 scope.
