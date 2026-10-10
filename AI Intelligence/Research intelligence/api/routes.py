import os
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text
from db.session import get_async_session, engine
from db.models import AIDocument, AIJob, AIChunk, JobStatus
from embeddings.indexer import EmbeddingIndexer
import redis.asyncio as aioredis

router = APIRouter(prefix="/api/v1/ai", tags=["AI Intelligence"])

INTERNAL_TOKEN = os.getenv("BACKEND_API_INTERNAL_TOKEN", "dev-internal-token")

def verify_internal_token(x_internal_service_token: str = Header(None)):
    if x_internal_service_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid internal service token")

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(select(AIJob).where(AIJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    return {"job_id": job.id, "status": job.status.value, "attempts": job.attempts, "error": job.error_message}

@router.post("/documents/ingest", dependencies=[Depends(verify_internal_token)])
async def ingest_document(payload: dict, db: AsyncSession = Depends(get_async_session)):
    backend_thesis_id = payload.get("backend_thesis_id")
    if not backend_thesis_id:
        raise HTTPException(400, "backend_thesis_id required")
        
    existing = await db.execute(select(AIDocument).where(AIDocument.backend_thesis_id == backend_thesis_id))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Document already ingested")

    doc = AIDocument(
        backend_thesis_id=backend_thesis_id,
        backend_user_id=payload.get("backend_user_id"),
        object_key=payload.get("object_key"),
        access_level=payload.get("access_level", "private")
    )
    db.add(doc)
    await db.flush()
    
    job = AIJob(document_id=doc.id, job_type="extraction")
    db.add(job)
    await db.commit()
    
    r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    await r.rpush("ai_intelligence:jobs", json.dumps({"job_id": job.id}))
    
    return {"job_id": job.id, "status": "queued"}

@router.post("/documents/{document_id}/embed", dependencies=[Depends(verify_internal_token)])
async def trigger_embedding_job(document_id: str, db: AsyncSession = Depends(get_async_session)):
    """Trigger embedding generation for a document"""
    result = await db.execute(select(AIDocument).where(AIDocument.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    
    # Create embedding job
    job = AIJob(document_id=doc.id, job_type="embedding")
    db.add(job)
    await db.commit()
    
    # Enqueue job
    r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    await r.rpush("ai_intelligence:jobs", json.dumps({"job_id": job.id}))
    
    return {"job_id": job.id, "status": "queued", "message": "Embedding job enqueued"}

@router.delete("/documents/{backend_thesis_id}", dependencies=[Depends(verify_internal_token)])
async def delete_document(backend_thesis_id: str, db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(select(AIDocument).where(AIDocument.backend_thesis_id == backend_thesis_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    
    # Invalidate embeddings first (cleanup vector index)
    indexer = EmbeddingIndexer()
    await indexer.invalidate_document(doc.id, db)
    
    # Cascade delete chunks and jobs via DB constraints
    await db.execute(delete(AIChunk).where(AIChunk.document_id == doc.id))
    await db.execute(delete(AIJob).where(AIJob.document_id == doc.id))
    await db.delete(doc)
    await db.commit()
    
    return {"status": "deleted", "message": "Document and all downstream AI state cleaned up"}

@router.get("/health")
async def health_check():
    checks = {"postgres": "unhealthy", "redis": "unhealthy"}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "healthy"
    except Exception:
        pass
        
    try:
        r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
        await r.ping()
        checks["redis"] = "healthy"
    except Exception:
        pass
        
    overall_status = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"
    return {"status": overall_status, "dependencies": checks}