# Phase 3 Evaluation Report
**Generated:** 2026-10-11T16:16:12.521235
**Corpus Version:** 1.0.0

## 1. Deterministic Suite Results
- **Tests Passed:** 16/16
- **Pass Rate:** 100.00%

## 2. Acceptance Thresholds (Provisional)
| Metric | Threshold | Status |
|--------|-----------|--------|
| Recall@1 (Retrieval) | >= 1.0 | PASS |
| Exact Match Score | >= 0.95 | PASS |
| Unrelated Pair Score | <= 0.3 | PASS |

## 3. Live-Provider Evaluations
- **Status:** SKIPPED (Requires `RUN_LIVE_EVALS=1` and valid API keys)
- **Reason:** Deterministic suite ensures structural integrity without incurring API costs or leaking keys.

## 4. Coverage Summary
- [x] Document Ingestion (OCR, Metadata, Sections)
- [x] Retrieval (Recall, Permissions)
- [x] RAG (Citations, Abstention)
- [x] NeMo Guardrails (Injections, Off-topic)
- [x] Research Gap & Similarity
- [x] Provider Reliability & API Access Control
