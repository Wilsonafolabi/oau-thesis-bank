import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Header, Request
from typing import Optional, List

from api.schemas import (
    JobResponse, JobStatus, ErrorResponse, SearchRequest, RAGRequest, DocumentUploadResponse
)
from api.jobs import create_job, update_job, get_job
from decision_layer.router import TypedDecisionRouter
from decision_layer.schemas import TaskType, RoutingDecision
from telemetry.health import health_manager
from telemetry.core import request_id_var, trace_id_var, setup_telemetry

logger = logging.getLogger("phase3_telemetry")
setup_telemetry()

router = APIRouter(prefix="/api/v1", tags=["Phase 3 Services"])

# --- Dependency: Request ID & Auth Mock ---
def get_request_ids(x_request_id: Optional[str] = Header(None)):
    req_id = x_request_id or str(uuid.uuid4())
    request_id_var.set(req_id)
    trace_id_var.set(f"trace-{req_id}")
    return req_id

def get_current_user(authorization: Optional[str] = Header(None)):
    # Mock auth: In production, decode JWT here.
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    return {"user_id": "mock_user_123", "roles": ["admin"]}

# --- 1. Health & Readiness ---
@router.get("/health", response_model=dict, summary="Application and dependency health")
async def health_check():
    return await health_manager.check_health()

# --- 2. Document Upload & Background Processing ---
@router.post("/documents/upload", response_model=DocumentUploadResponse, status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    req_id: str = Depends(get_request_ids)
):
    # Real validation: file size, type checks would happen here.
    job_id = create_job("document_ingestion")
    
    # Simulate background ingestion calling real service
    def process_ingestion(jid: str):
        try:
            # TODO: Call real document_processing.ingest() here
            update_job(jid, JobStatus.COMPLETED, result={"chunks": 42}, message="Ingestion complete")
        except Exception as e:
            update_job(jid, JobStatus.FAILED, message=str(e))
            
    background_tasks.add_task(process_ingestion, job_id)
    
    return DocumentUploadResponse(document_id="doc_new_123", job_id=job_id, status=JobStatus.PROCESSING)

@router.get("/documents/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

# --- 3. RAG & Decision Layer Integration ---
@router.post("/rag/ask", response_model=dict)
async def ask_rag_question(
    request: RAGRequest,
    user: dict = Depends(get_current_user),
    req_id: str = Depends(get_request_ids)
):
    # 1. Run NeMo Guardrails & JEV/Laya routing via Decision Layer
    decision_router = TypedDecisionRouter()
    decision = await decision_router.route(
        task_type=TaskType.QUERY_CLASSIFICATION,
        state={"query": request.question},
        user_id=user["user_id"]
    )
    
    # 2. Enforce Decision
    if decision.decision == RoutingDecision.BLOCK:
        logger.warning("RAG request blocked", extra={"reason": decision.fallback_reason.value})
        raise HTTPException(status_code=403, detail=f"Request blocked: {decision.fallback_reason.value}")
        
    # 3. If allowed, proceed to real RAG generation (Mocked response for scaffold)
    # TODO: Call real rag_service.generate() here
    return {
        "answer": "Based on the indexed theses, machine learning is applied in agriculture...",
        "citations": ["doc_pub_1"],
        "decision_engine": decision.engine_used,
        "confidence": decision.confidence,
        "request_id": req_id
    }

# --- 4. Researcher Intelligence ---
@router.get("/intelligence/researchers", response_model=List[dict])
async def list_researchers(limit: int = 10, offset: int = 0):
    # TODO: Call real researcher_intelligence.api.list_researchers()
    return [{"id": "res_1", "name": "Dr. Afolabi Wilson", "department": "Computer Science"}]

# --- 5. Evaluation Status (Admin Only) ---
@router.get("/evaluations/status", response_model=dict)
async def evaluation_status(user: dict = Depends(get_current_user)):
    if "admin" not in user.get("roles", []):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # TODO: Read real EVALUATION_LOG.md or DB
    return {
        "last_run": "2024-05-20T10:00:00Z",
        "deterministic_pass_rate": "100%",
        "live_evals_status": "SKIPPED"
    }

# --- 6. Research Gap Detection (Truthful Empty State) ---
@router.get("/research-gaps", response_model=List[dict])
async def detect_research_gaps(topic: Optional[str] = None):
    "Truthful response: Research gap detection model is not yet connected."
    logger.info(f"research_gaps_requested topic={topic}")
    return []
