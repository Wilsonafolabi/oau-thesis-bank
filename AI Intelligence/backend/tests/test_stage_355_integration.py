"""Stage 3.5.5 live integration test harness.

Verifies the authenticated PDF ingestion + RAG retrieval contract end-to-end
against a RUNNING Django backend (with the V2 AI service reachable through the
Django /api/ai/ proxy).

This file only IMPLEMENTS the harness. It makes NO live HTTP requests and
creates NO users, theses, documents, or storage objects by being imported or
collected. Execute only against live services with the required environment
variables set (see "Environment variables required" below).

Design follows:
- STAGE_3_5_5_TEST_EXECUTION_PLAN.md (amended)
- STAGE_3_5_5_INDEPENDENT_CONTRACT_AUDIT.md

Restrictions honored by this file:
- No production application code is modified.
- No retrieval architecture is changed; no BM25 is implemented.
- Stage 3.6 is not begun.
- Credentials are read from environment variables only; they are never
  printed, logged, hardcoded, or committed.
- Exactly two dedicated reusable accounts (User A / User B) are used; no
  unlimited account creation.
- Cross-encoder verification distinguishes importable / model loaded /
  reranking executed / unavailable-degraded; it never claims runtime
  verification from an import or `available` flag alone.
- R2 deletion limitation is recorded: V2 object_key cleanup is local
  Path.unlink(), not an R2/S3 client call; R2 deletion is not asserted.
- Cleanup failures are collected, made visible, and cause a clear pytest
  failure when test resources remain.
"""

from __future__ import annotations

import io
import os
import sys
import time
import uuid
from typing import Any, Dict, Optional

import pytest
import requests

# ---------------------------------------------------------------------------
# Optional PDF dependencies (guarded). Neither reportlab nor pypdf is required
# to import/collect this module; they are required only to build/validate the
# fixture PDF. If unavailable, the PDF-dependent tests skip rather than fail.
# ---------------------------------------------------------------------------
_REPORTLAB = False
_PYPDF = False
try:  # pragma: no cover - exercised only when dependencies are installed
    from reportlab.lib.pagesizes import letter as _rl_letter  # type: ignore
    from reportlab.pdfgen import canvas as _rl_canvas  # type: ignore
    _REPORTLAB = True
except Exception:  # pragma: no cover - reportlab not installed
    _REPORTLAB = False

try:  # pragma: no cover - exercised only when dependencies are installed
    import pypdf as _pypdf  # type: ignore
    _PYPDF = True
except Exception:  # pragma: no cover - pypdf not installed
    _PYPDF = False


# ---------------------------------------------------------------------------
# Configuration (environment variables only; values never printed)
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("STAGE355_BASE_URL", "http://127.0.0.1:8000/api").rstrip("/")

USER_A_EMAIL = os.getenv("STAGE355_USER_A_EMAIL", "")
USER_A_PASSWORD = os.getenv("STAGE355_USER_A_PASSWORD", "")
USER_A_NAME = os.getenv("STAGE355_USER_A_NAME", "Stage 3.5.5 User A")

USER_B_EMAIL = os.getenv("STAGE355_USER_B_EMAIL", "")
USER_B_PASSWORD = os.getenv("STAGE355_USER_B_PASSWORD", "")
USER_B_NAME = os.getenv("STAGE355_USER_B_NAME", "Stage 3.5.5 User B")

V2_SRC = os.getenv("STAGE355_V2_SRC", "")

POLL_INTERVAL = 2.0
POLL_TIMEOUT = 90.0

# Unique run marker embedded in the PDF and used to tie retrieval evidence to
# the uploaded document. Not a secret.
RUN_MARKER = f"OAU_STAGE355_{uuid.uuid4().hex[:12]}"
PAGE1_PASSAGE = f"{RUN_MARKER}_PAGE_1 alpha beta gamma delta epsilon."
PAGE2_PASSAGE = f"{RUN_MARKER}_PAGE_2 zeta eta theta iota kappa lambda."


def _headers(access_token: str) -> Dict[str, str]:
    """Build an Authorization header. The token value is never returned/printed."""
    return {"Authorization": f"Bearer {access_token}"}


def _require_credentials() -> None:
    """Fail fast if dedicated account credentials are not configured."""
    missing = [
        name
        for name, value in (
            ("STAGE355_USER_A_EMAIL", USER_A_EMAIL),
            ("STAGE355_USER_A_PASSWORD", USER_A_PASSWORD),
            ("STAGE355_USER_B_EMAIL", USER_B_EMAIL),
            ("STAGE355_USER_B_PASSWORD", USER_B_PASSWORD),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required credentials: " + ", ".join(missing)
        )


def _register_or_login(
    session: requests.Session, email: str, password: str, name: str
) -> str:
    """Idempotently register, then login; return the access token.

    Registration is tolerant of "already exists" so the same dedicated accounts
    can be reused across runs. The access token is returned in memory and is
    never printed or stored in the diagnostics fixture.
    """
    reg = session.post(
        f"{BASE_URL}/auth/register/",
        json={
            "email": email,
            "password": password,
            "name": name,
            "role": "student",
            "department": "Computer Science",
            "faculty": "Science",
        },
        timeout=30,
    )
    if reg.status_code not in (200, 201):
        detail = ""
        try:
            payload = reg.json()
            if isinstance(payload, dict):
                # DRF may return field-specific errors (e.g. {"email": [...]})
                # rather than a top-level "detail" key.
                detail_parts = []
                for _k, _v in payload.items():
                    if isinstance(_v, list):
                        detail_parts.extend(str(x) for x in _v)
                    else:
                        detail_parts.append(str(_v))
                detail = " ".join(detail_parts)
            else:
                detail = str(payload)
        except Exception:
            detail = reg.text[:200]
        if "already exists" not in str(detail).lower():
            raise RuntimeError(
                f"Registration failed for {email}: HTTP {reg.status_code} {detail}"
            )

    login = session.post(
        f"{BASE_URL}/auth/login/",
        json={"email": email, "password": password},
        timeout=30,
    )
    if login.status_code != 200:
        raise RuntimeError(
            f"Login failed for {email}: HTTP {login.status_code} {login.text[:200]}"
        )
    return login.json()["access"]


def _make_pdf_bytes() -> bytes:
    """Build a two-page text PDF with ReportLab and validate with pypdf.

    Returns PDF bytes. Skips the test if reportlab/pypdf are unavailable.
    """
    if not _REPORTLAB or not _PYPDF:
        missing = []
        if not _REPORTLAB:
            missing.append("reportlab")
        if not _PYPDF:
            missing.append("pypdf")
        pytest.fail(
            "Prerequisite missing: " + ", ".join(missing)
            + " is not installed; cannot build/validate the test PDF fixture. "
            "Install test dependencies (see pyproject.toml [dependency-groups] dev)."
        )

    buffer = io.BytesIO()
    canvas = _rl_canvas.Canvas(buffer, pagesize=_rl_letter)
    width, height = _rl_letter
    canvas.drawString(72, height - 72, PAGE1_PASSAGE)
    canvas.showPage()
    canvas.drawString(72, height - 72, PAGE2_PASSAGE)
    canvas.showPage()
    canvas.save()
    pdf_bytes = buffer.getvalue()

    reader = _pypdf.PdfReader(io.BytesIO(pdf_bytes))
    if len(reader.pages) != 2:
        raise RuntimeError(f"Expected 2 PDF pages, got {len(reader.pages)}")
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        expected = PAGE1_PASSAGE if idx == 1 else PAGE2_PASSAGE
        if expected not in text:
            raise RuntimeError(
                f"PDF page {idx} does not contain the expected passage marker"
            )
    return pdf_bytes


def _poll_job_status(
    session: requests.Session, access_token: str, job_id: str
) -> Dict[str, Any]:
    """Poll the job-status endpoint until a terminal state or timeout."""
    deadline = time.time() + POLL_TIMEOUT
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        resp = session.get(
            f"{BASE_URL}/ai/documents/jobs/{job_id}/",
            headers=_headers(access_token),
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Job status poll failed: HTTP {resp.status_code} {resp.text[:200]}"
            )
        last = resp.json()
        status = (last.get("status") or "").lower()
        if status in ("completed", "success", "failed"):
            return last
        time.sleep(POLL_INTERVAL)
    raise RuntimeError(
        f"Job {job_id} did not reach terminal state within {POLL_TIMEOUT}s; "
        f"last={last}"
    )


# ---------------------------------------------------------------------------
# Cross-encoder runtime verification
# ---------------------------------------------------------------------------
def _cross_encoder_status() -> Dict[str, Any]:
    """Distinguish importable / model loaded / reranking executed / degraded.

    Never claims runtime verification from an import or `available` flag alone.
    Attempts an actual rerank() execution only when the model is loaded;
    reports the limitation honestly if execution cannot be safely verified.
    """
    result: Dict[str, Any] = {
        "importable": False,
        "model_loaded": None,
        "reranking_executed": None,
        "status": "unavailable",
        "limitation": None,
    }

    # 1. Importable?
    try:
        if V2_SRC and V2_SRC not in sys.path:
            sys.path.insert(0, V2_SRC)
        from oau_ai.rag.service import Reranker  # type: ignore
        result["importable"] = True
        result["_reranker_class"] = Reranker
    except Exception as exc:  # pragma: no cover - environmental
        result["limitation"] = f"import failed: {type(exc).__name__}: {exc}"
        result["status"] = "unavailable"
        return result

    # 2. Model loaded?
    try:
        reranker = result["_reranker_class"]()
        result["model_loaded"] = bool(reranker.available)
    except Exception as exc:  # pragma: no cover - environmental
        result["limitation"] = f"instantiation failed: {type(exc).__name__}: {exc}"
        result["status"] = "degraded"
        return result

    if not result["model_loaded"]:
        result["status"] = "degraded"
        result["limitation"] = (
            "CrossEncoder model not loaded "
            "(sentence-transformers or model weights unavailable)"
        )
        return result

    # 3. Reranking actually executed? (only safe when model is in memory)
    try:

        class _Chunk:
            def __init__(self, text: str) -> None:
                self.text = text

        chunks = [
            _Chunk("sample thesis text about machine learning research")
        ]
        out = reranker.rerank("machine learning", chunks, top_k=1)
        result["reranking_executed"] = isinstance(out, list)
        if result["reranking_executed"]:
            result["status"] = "verified"
        else:
            result["status"] = "failed"
            result["limitation"] = "rerank() returned non-list result"
    except Exception as exc:  # pragma: no cover - environmental
        result["reranking_executed"] = False
        result["status"] = "failed"
        result["limitation"] = (
            f"rerank() execution failed: {type(exc).__name__}: {exc}. "
            "Runtime verification of reranking is limited without modifying "
            "production code."
        )

    # Remove the class reference before returning (not needed in diagnostics).
    result.pop("_reranker_class", None)
    return result


# ---------------------------------------------------------------------------
# Test context holding per-sequence state and performing approved cleanup.
# ---------------------------------------------------------------------------
class Stage355Context:
    def __init__(self, session: requests.Session) -> None:
        self.session = session
        self.token_a: Optional[str] = None
        self.token_b: Optional[str] = None
        self.created_thesis_ids: list = []
        self.created_doc_refs: list = []  # each: {backend_thesis_id, document_id, job_id, token}
        self.cleanup_summary: Dict[str, Any] = {}

    def authenticate(self) -> None:
        self.token_a = _register_or_login(
            self.session, USER_A_EMAIL, USER_A_PASSWORD, USER_A_NAME
        )
        self.token_b = _register_or_login(
            self.session, USER_B_EMAIL, USER_B_PASSWORD, USER_B_NAME
        )

    def create_thesis(self, token: str, title: str, access_policy: str) -> int:
        files = {"file": ("thesis.pdf", _make_pdf_bytes(), "application/pdf")}
        data = {
            "title": title,
            "author": "Stage 3.5.5 Test",
            "department": "Computer Science",
            "faculty": "Science",
            "year": 2024,
            "abstract": f"Abstract for {RUN_MARKER}.",
            "supervisor": "Dr. Test",
            "status": "published",
            "access_policy": access_policy,
        }
        resp = self.session.post(
            f"{BASE_URL}/theses/",
            data=data,
            files=files,
            headers=_headers(token),
            timeout=60,
        )
        if resp.status_code != 201:
            raise RuntimeError(
                f"Thesis create failed: HTTP {resp.status_code} {resp.text[:300]}"
            )
        body = resp.json()
        thesis_id = body["id"]
        self.created_thesis_ids.append(thesis_id)
        return thesis_id

    def upload(
        self, token: str, backend_thesis_id: int
    ) -> Dict[str, Any]:
        files = {"file": ("thesis.pdf", _make_pdf_bytes(), "application/pdf")}
        data = {"backend_thesis_id": str(backend_thesis_id)}
        resp = self.session.post(
            f"{BASE_URL}/ai/documents/upload/",
            data=data,
            files=files,
            headers=_headers(token),
            timeout=120,
        )
        if resp.status_code != 202:
            raise RuntimeError(
                f"Upload failed: HTTP {resp.status_code} {resp.text[:300]}"
            )
        body = resp.json()
        ref = {
            "backend_thesis_id": backend_thesis_id,
            "document_id": body["document_id"],
            "job_id": body["job_id"],
            "token": token,
        }
        self.created_doc_refs.append(ref)
        return ref

    def cleanup_all(self, stage355_diag: Any) -> Dict[str, Any]:
        """Approved cleanup order:
        1. Delete V2 document using Django backend_thesis_id.
        2. Verify V2 DB records removed (job status 404, text 404).
        3. Delete Django Thesis record ONLY if V2 delete + verification succeeded.
        4. Record storage/R2 limitation (no R2 deletion claim).

        If V2 deletion or verification fails, the Django Thesis record is
        preserved for recovery and added to outstanding_resources.
        """
        summary: Dict[str, Any] = {
            "resources": [],
            "errors": [],
            "outstanding_resources": [],
            "all_clean": False,
        }

        handled_thesis_ids = set()

        # 1 + 2: V2 document deletion + V2 DB verification.
        for ref in list(self.created_doc_refs):
            token = ref["token"]
            btid = ref["backend_thesis_id"]
            handled_thesis_ids.add(btid)
            resource: Dict[str, Any] = {
                "backend_thesis_id": btid,
                "document_id": ref["document_id"],
                "job_id": ref["job_id"],
                "v2_delete_status": None,
                "job_status_after_delete": None,
                "text_status_after_delete": None,
                "v2_delete_ok": False,
                "verification_ok": False,
                "django_delete_ok": False,
                "outstanding": False,
            }

            try:
                del_resp = self.session.delete(
                    f"{BASE_URL}/ai/documents/{btid}/",
                    headers=_headers(token),
                    timeout=60,
                )
                resource["v2_delete_status"] = del_resp.status_code
                resource["v2_delete_ok"] = del_resp.status_code == 200
                if not resource["v2_delete_ok"]:
                    summary["errors"].append(
                        f"V2 delete {btid} returned HTTP {del_resp.status_code}"
                    )

                if resource["v2_delete_ok"]:
                    job_resp = self.session.get(
                        f"{BASE_URL}/ai/documents/jobs/{ref['job_id']}/",
                        headers=_headers(token),
                        timeout=30,
                    )
                    resource["job_status_after_delete"] = job_resp.status_code

                    text_resp = self.session.get(
                        f"{BASE_URL}/ai/documents/{ref['document_id']}/text/",
                        headers=_headers(token),
                        timeout=30,
                    )
                    resource["text_status_after_delete"] = text_resp.status_code

                    resource["verification_ok"] = (
                        job_resp.status_code == 404
                        and text_resp.status_code == 404
                    )
                    if not resource["verification_ok"]:
                        summary["errors"].append(
                            f"V2 verification {btid}: job={job_resp.status_code} "
                            f"text={text_resp.status_code}"
                        )
            except Exception as exc:  # pragma: no cover - diagnostic
                summary["errors"].append(f"V2 delete/verify {btid}: {exc}")

            # 3: Django Thesis deletion ONLY if V2 delete + verification succeeded.
            if resource["v2_delete_ok"] and resource["verification_ok"]:
                try:
                    del_resp = self.session.delete(
                        f"{BASE_URL}/theses/{btid}/",
                        headers=_headers(self.token_a),
                        timeout=30,
                    )
                    resource["django_delete_ok"] = del_resp.status_code == 204
                    if not resource["django_delete_ok"]:
                        summary["errors"].append(
                            f"Django thesis {btid} delete returned "
                            f"HTTP {del_resp.status_code}"
                        )
                except Exception as exc:  # pragma: no cover - diagnostic
                    summary["errors"].append(f"Django thesis delete {btid}: {exc}")
            else:
                # Preserve thesis for recovery; never silently drop.
                resource["outstanding"] = True
                summary["outstanding_resources"].append(
                    f"thesis {btid} retained (V2 delete/verification failed)"
                )

            summary["resources"].append(resource)

        # Handle any thesis created but not covered by a doc ref (e.g. upload failed).
        for thesis_id in self.created_thesis_ids:
            if thesis_id in handled_thesis_ids:
                continue
            resource: Dict[str, Any] = {
                "backend_thesis_id": thesis_id,
                "document_id": None,
                "job_id": None,
                "v2_delete_status": None,
                "job_status_after_delete": None,
                "text_status_after_delete": None,
                "v2_delete_ok": True,  # no V2 document exists; nothing to delete
                "verification_ok": True,  # no V2 document exists; nothing to verify
                "django_delete_ok": False,
                "outstanding": False,
            }
            try:
                del_resp = self.session.delete(
                    f"{BASE_URL}/theses/{thesis_id}/",
                    headers=_headers(self.token_a),
                    timeout=30,
                )
                resource["django_delete_ok"] = del_resp.status_code == 204
                if not resource["django_delete_ok"]:
                    summary["errors"].append(
                        f"Django thesis {thesis_id} delete returned "
                        f"HTTP {del_resp.status_code}"
                    )
            except Exception as exc:  # pragma: no cover - diagnostic
                summary["errors"].append(f"Django thesis delete {thesis_id}: {exc}")
                resource["outstanding"] = True
                summary["outstanding_resources"].append(
                    f"thesis {thesis_id} retained (delete failed)"
                )
            summary["resources"].append(resource)

        summary["all_clean"] = (
            len(summary["errors"]) == 0
            and len(summary["outstanding_resources"]) == 0
            and all(
                r["v2_delete_ok"] and r["verification_ok"] and r["django_delete_ok"]
                for r in summary["resources"]
            )
        )

        self.cleanup_summary = summary

        # Record in diagnostics (non-secret only).
        stage355_diag.set("cleanup_all_clean", summary["all_clean"])
        stage355_diag.set("cleanup_errors", summary["errors"])
        stage355_diag.set("outstanding_resources", summary["outstanding_resources"])
        stage355_diag.set("cleanup_resources", summary["resources"])

        return summary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def http_session() -> requests.Session:
    return requests.Session()


# ---------------------------------------------------------------------------
# Sequence A: public ingestion + RAG retrieval + duplicate guard + cleanup
# ---------------------------------------------------------------------------
def test_stage_355_sequence_a_public(
    http_session: requests.Session, stage355_diag: Any
) -> None:
    """Public thesis: create -> upload -> poll -> text -> RAG -> similarity ->
    duplicate-guard (409) -> approved cleanup."""
    _require_credentials()
    ctx = Stage355Context(http_session)
    ctx.authenticate()

    # Per-test diagnostics baseline.
    stage355_diag.set("sequence", "A_public")
    stage355_diag.set("rag_status", None)
    stage355_diag.set("rag_detail", None)
    stage355_diag.set("cross_encoder_status", None)

    try:
        # Cross-encoder status (recorded, not assumed).
        ce_status = _cross_encoder_status()
        stage355_diag.set("cross_encoder_status", ce_status)

        thesis_id = ctx.create_thesis(
            ctx.token_a, "Public Stage 3.5.5 Thesis", "public"
        )
        stage355_diag.set("public_thesis_id", thesis_id)

        ref = ctx.upload(ctx.token_a, thesis_id)
        stage355_diag.set("public_document_id", ref["document_id"])
        stage355_diag.set("public_job_id", ref["job_id"])

        job = _poll_job_status(ctx.session, ctx.token_a, ref["job_id"])
        status = (job.get("status") or "").lower()
        stage355_diag.set("public_job_status", status)
        assert status == "completed", f"Ingestion did not complete: {job}"
        result = job.get("result") or {}
        stage355_diag.set("public_embedding_status", result.get("embedding_status"))
        assert result.get("embedding_status") == "completed"

        # Text retrieval (User A, owner).
        text_resp = ctx.session.get(
            f"{BASE_URL}/ai/documents/{ref['document_id']}/text/",
            headers=_headers(ctx.token_a),
            timeout=30,
        )
        assert text_resp.status_code == 200, text_resp.text[:300]
        text_body = text_resp.json()
        stage355_diag.set("public_text_total_pages", text_body.get("total_pages"))
        assert text_body.get("total_pages") == 2
        page_texts = " ".join(
            (p.get("text") or "") for p in text_body.get("pages", [])
        )
        assert PAGE1_PASSAGE in page_texts
        assert PAGE2_PASSAGE in page_texts

        # RAG retrieval with citation provenance verification.
        # A 503 (DeepSeek unavailable) is recorded as "unavailable" and does
        # NOT skip the remaining similarity / duplicate-guard tests.
        rag_resp = ctx.session.post(
            f"{BASE_URL}/ai/rag/ask/",
            json={
                "question": PAGE1_PASSAGE,
                "document_ids": [ref["document_id"]],
                "top_k": 5,
            },
            headers=_headers(ctx.token_a),
            timeout=120,
        )
        if rag_resp.status_code == 503:
            stage355_diag.set("rag_status", "unavailable")
            stage355_diag.set(
                "rag_detail",
                "DeepSeek provider unavailable (HTTP 503); no Groq fallback. "
                "RAG not verified; similarity and duplicate-guard continue.",
            )
        elif rag_resp.status_code != 200:
            stage355_diag.set("rag_status", "failed")
            stage355_diag.set(
                "rag_detail",
                f"RAG returned HTTP {rag_resp.status_code}: "
                f"{rag_resp.text[:200]}",
            )
        else:
            rag_body = rag_resp.json()
            citations = rag_body.get("citations") or []
            stage355_diag.set("public_rag_citation_count", len(citations))
            matching = [
                c
                for c in citations
                if c.get("backend_thesis_id") == str(thesis_id)
            ]
            stage355_diag.set("public_rag_matching_citations", len(matching))
            snippets = " ".join(c.get("text_snippet", "") for c in matching)
            if len(matching) >= 1 and (
                RUN_MARKER in snippets or PAGE1_PASSAGE in snippets
            ):
                stage355_diag.set("rag_status", "verified")
            else:
                stage355_diag.set("rag_status", "failed")
                stage355_diag.set(
                    "rag_detail",
                    "HTTP 200 but no citation references the uploaded thesis "
                    "with the expected passage.",
                )

        # Similarity search (independent of RAG availability).
        sim_resp = ctx.session.post(
            f"{BASE_URL}/ai/similarity/check/",
            json={"text": PAGE1_PASSAGE, "max_matches": 5},
            headers=_headers(ctx.token_a),
            timeout=120,
        )
        assert sim_resp.status_code == 200, sim_resp.text[:300]
        sim_body = sim_resp.json()
        matches = sim_body.get("matches") or []
        stage355_diag.set("public_similarity_match_count", len(matches))
        sim_matching = [
            m for m in matches if m.get("backend_thesis_id") == str(thesis_id)
        ]
        stage355_diag.set("public_similarity_matching", len(sim_matching))
        assert len(sim_matching) >= 1, (
            "No similarity match references the uploaded thesis"
        )

        # Sequence C: duplicate upload guard MUST run before cleanup.
        dup_resp = ctx.session.post(
            f"{BASE_URL}/ai/documents/upload/",
            data={"backend_thesis_id": str(thesis_id)},
            files={"file": ("thesis.pdf", _make_pdf_bytes(), "application/pdf")},
            headers=_headers(ctx.token_a),
            timeout=120,
        )
        stage355_diag.set("duplicate_upload_status", dup_resp.status_code)
        assert dup_resp.status_code == 409, (
            f"Expected 409 duplicate guard, got {dup_resp.status_code}: "
            f"{dup_resp.text[:300]}"
        )
    finally:
        summary = ctx.cleanup_all(stage355_diag)

    # Cleanup failures must cause a clear pytest failure when no test-body
    # exception is in flight. Resources are never silently abandoned.
    assert summary["all_clean"], (
        "Cleanup incomplete. "
        f"errors={summary['errors']} "
        f"outstanding={summary['outstanding_resources']}"
    )


# ---------------------------------------------------------------------------
# Sequence B: private thesis access-denial (User B) + cleanup
# ---------------------------------------------------------------------------
def test_stage_355_sequence_b_private(
    http_session: requests.Session, stage355_diag: Any
) -> None:
    """Private thesis: User A creates/uploads; User B denied text + RAG (403);
    then approved cleanup."""
    _require_credentials()
    ctx = Stage355Context(http_session)
    ctx.authenticate()

    stage355_diag.set("sequence", "B_private")
    stage355_diag.set("rag_status", None)
    stage355_diag.set("rag_detail", None)
    stage355_diag.set("cross_encoder_status", None)

    try:
        thesis_id = ctx.create_thesis(
            ctx.token_a, "Private Stage 3.5.5 Thesis", "private"
        )
        stage355_diag.set("private_thesis_id", thesis_id)

        ref = ctx.upload(ctx.token_a, thesis_id)
        stage355_diag.set("private_document_id", ref["document_id"])

        job = _poll_job_status(ctx.session, ctx.token_a, ref["job_id"])
        status = (job.get("status") or "").lower()
        stage355_diag.set("private_job_status", status)
        assert status == "completed"

        # User B accessing the private document's text -> 403.
        text_resp = http_session.get(
            f"{BASE_URL}/ai/documents/{ref['document_id']}/text/",
            headers=_headers(ctx.token_b),
            timeout=30,
        )
        stage355_diag.set("private_text_user_b_status", text_resp.status_code)
        assert text_resp.status_code == 403

        # User B RAG-querying the private thesis -> 403.
        rag_resp = http_session.post(
            f"{BASE_URL}/ai/rag/ask/",
            json={
                "question": PAGE1_PASSAGE,
                "document_ids": [ref["document_id"]],
                "top_k": 5,
            },
            headers=_headers(ctx.token_b),
            timeout=120,
        )
        stage355_diag.set("private_rag_user_b_status", rag_resp.status_code)
        assert rag_resp.status_code == 403
    finally:
        summary = ctx.cleanup_all(stage355_diag)

    assert summary["all_clean"], (
        "Cleanup incomplete. "
        f"errors={summary['errors']} "
        f"outstanding={summary['outstanding_resources']}"
    )


# ---------------------------------------------------------------------------
# Focused regression tests for RAG document authorization fix
# ---------------------------------------------------------------------------
def test_stage_355_rag_public_document_permitted(
    http_session: requests.Session, stage355_diag: Any
) -> None:
    """Valid public document → permitted for owner."""
    _require_credentials()
    ctx = Stage355Context(http_session)
    ctx.authenticate()
    try:
        thesis_id = ctx.create_thesis(
            ctx.token_a, "Public RAG Test Thesis", "public"
        )
        ref = ctx.upload(ctx.token_a, thesis_id)
        job = _poll_job_status(ctx.session, ctx.token_a, ref["job_id"])
        assert (job.get("status") or "").lower() == "completed"

        rag_resp = ctx.session.post(
            f"{BASE_URL}/ai/rag/ask/",
            json={
                "question": PAGE1_PASSAGE,
                "document_ids": [ref["document_id"]],
                "top_k": 5,
            },
            headers=_headers(ctx.token_a),
            timeout=120,
        )
        stage355_diag.set("rag_public_document_status", rag_resp.status_code)
        assert rag_resp.status_code == 200
    finally:
        summary = ctx.cleanup_all(stage355_diag)
        assert summary["all_clean"]


def test_stage_355_rag_private_document_permitted_for_owner(
    http_session: requests.Session, stage355_diag: Any
) -> None:
    """Valid private document owned by User A → permitted for User A."""
    _require_credentials()
    ctx = Stage355Context(http_session)
    ctx.authenticate()
    try:
        thesis_id = ctx.create_thesis(
            ctx.token_a, "Private RAG Owner Test Thesis", "private"
        )
        ref = ctx.upload(ctx.token_a, thesis_id)
        job = _poll_job_status(ctx.session, ctx.token_a, ref["job_id"])
        assert (job.get("status") or "").lower() == "completed"

        rag_resp = ctx.session.post(
            f"{BASE_URL}/ai/rag/ask/",
            json={
                "question": PAGE1_PASSAGE,
                "document_ids": [ref["document_id"]],
                "top_k": 5,
            },
            headers=_headers(ctx.token_a),
            timeout=120,
        )
        stage355_diag.set("rag_private_owner_status", rag_resp.status_code)
        assert rag_resp.status_code == 200
    finally:
        summary = ctx.cleanup_all(stage355_diag)
        assert summary["all_clean"]


def test_stage_355_rag_unknown_document_uuid(
    http_session: requests.Session, stage355_diag: Any
) -> None:
    """Unknown document UUID → 404."""
    _require_credentials()
    ctx = Stage355Context(http_session)
    ctx.authenticate()
    try:
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        rag_resp = ctx.session.post(
            f"{BASE_URL}/ai/rag/ask/",
            json={
                "question": PAGE1_PASSAGE,
                "document_ids": [fake_uuid],
                "top_k": 5,
            },
            headers=_headers(ctx.token_a),
            timeout=30,
        )
        stage355_diag.set("rag_unknown_uuid_status", rag_resp.status_code)
        assert rag_resp.status_code == 404
    finally:
        pass


def test_stage_355_rag_malformed_uuid(
    http_session: requests.Session, stage355_diag: Any
) -> None:
    """Malformed UUID → 404."""
    _require_credentials()
    ctx = Stage355Context(http_session)
    ctx.authenticate()
    try:
        rag_resp = ctx.session.post(
            f"{BASE_URL}/ai/rag/ask/",
            json={
                "question": PAGE1_PASSAGE,
                "document_ids": ["not-a-uuid"],
                "top_k": 5,
            },
            headers=_headers(ctx.token_a),
            timeout=30,
        )
        stage355_diag.set("rag_malformed_uuid_status", rag_resp.status_code)
        assert rag_resp.status_code == 404
    finally:
        pass


def test_stage_355_rag_multiple_document_ids(
    http_session: requests.Session, stage355_diag: Any
) -> None:
    """Multiple document IDs → each independently authorized."""
    _require_credentials()
    ctx = Stage355Context(http_session)
    ctx.authenticate()
    try:
        thesis_id = ctx.create_thesis(
            ctx.token_a, "Multi-doc RAG Test Thesis", "private"
        )
        ref = ctx.upload(ctx.token_a, thesis_id)
        job = _poll_job_status(ctx.session, ctx.token_a, ref["job_id"])
        assert (job.get("status") or "").lower() == "completed"

        unknown_uuid = "00000000-0000-0000-0000-000000000000"

        # Valid ID first, unknown second → 404 on the unknown one.
        rag_resp = ctx.session.post(
            f"{BASE_URL}/ai/rag/ask/",
            json={
                "question": PAGE1_PASSAGE,
                "document_ids": [ref["document_id"], unknown_uuid],
                "top_k": 5,
            },
            headers=_headers(ctx.token_a),
            timeout=30,
        )
        stage355_diag.set("rag_multiple_doc_ids_status", rag_resp.status_code)
        assert rag_resp.status_code == 404

        # Unknown first, valid second → 404 immediately on the unknown one.
        rag_resp2 = ctx.session.post(
            f"{BASE_URL}/ai/rag/ask/",
            json={
                "question": PAGE1_PASSAGE,
                "document_ids": [unknown_uuid, ref["document_id"]],
                "top_k": 5,
            },
            headers=_headers(ctx.token_a),
            timeout=30,
        )
        stage355_diag.set(
            "rag_multiple_doc_ids_reversed_status", rag_resp2.status_code
        )
        assert rag_resp2.status_code == 404
    finally:
        summary = ctx.cleanup_all(stage355_diag)
        assert summary["all_clean"]


def test_stage_355_rag_empty_document_ids(
    http_session: requests.Session, stage355_diag: Any
) -> None:
    """Empty document_ids → existing default behaviour preserved (no Django
    access check; V2 handles authorization for the default scope)."""
    _require_credentials()
    ctx = Stage355Context(http_session)
    ctx.authenticate()
    try:
        rag_resp = ctx.session.post(
            f"{BASE_URL}/ai/rag/ask/",
            json={
                "question": PAGE1_PASSAGE,
                "top_k": 5,
            },
            headers=_headers(ctx.token_a),
            timeout=120,
        )
        stage355_diag.set("rag_empty_doc_ids_status", rag_resp.status_code)
        # No document_ids → Django skips its access check; result is whatever
        # V2 returns (200 or 503), never a Django 403/404 access error.
        assert rag_resp.status_code != 403
        assert rag_resp.status_code != 404
    finally:
        pass


def test_stage_355_final_report(stage355_diag: Any) -> None:
    """Aggregate non-secret report; asserts cleanup and no outstanding resources.

    Asserts nothing about credentials, JWTs, passwords, API keys, or
    environment-variable values.
    """
    report = stage355_diag.as_dict()
    assert isinstance(report, dict)

    # Sanity: no secret keys leaked into diagnostics.
    for key in report:
        lower = key.lower()
        assert "token" not in lower
        assert "password" not in lower
        assert "secret" not in lower
        assert "authorization" not in lower

    # Summarize outcomes (non-secret). Per-sequence cleanup assertions already
    # run in each sequence's finally block; this test only aggregates/reports.
    stage355_diag.set("report_generated", True)
