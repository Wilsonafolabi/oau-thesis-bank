from recommendation.service import RecommendationService
import os
import json
import hashlib
import structlog
import redis
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
import tempfile
import asyncio

# --- TELEMETRY SETUP: Pure JSON Structured Logging ---
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger()

# --- SEMANTIC CACHE SETUP (Redis) ---
cache = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Import our AI modules
from inference_router import evaluate_decision, generate_with_fallback
from rag_pipeline import retrieve_context
from similarity_checker import check_similarity
from phase3_6_researcher_intelligence import extract_metadata_from_pdf, save_metadata, build_and_print_graphs

app = FastAPI(title="OAU Thesis Bank - AI Intelligence Layer", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str
    stream: bool = False

def get_cache_key(query: str) -> str:
    return f"rag_cache:{hashlib.md5(query.lower().strip().encode()).hexdigest()}"

async def generate_stream(query: str, context: str, system_prompt: str):
    """Async generator for token-by-token streaming simulation"""
    answer = generate_with_fallback(system_prompt, f"Context:\n{context}\n\nQuestion: {query}")
    for i in range(0, len(answer), 50):
        yield json.dumps({"token": answer[i:i+50]}) + "\n"
        await asyncio.sleep(0.05)

@app.post("/api/v1/ai/rag-query")
async def rag_query(request: QueryRequest):
    cache_key = get_cache_key(request.query)
    
    # 1. SEMANTIC CACHE CHECK
    cached_answer = cache.get(cache_key)
    if cached_answer:
        logger.info("cache_hit", query=request.query)
        if request.stream:
            return StreamingResponse(iter([json.dumps({"token": cached_answer, "cached": True}) + "\n"]), media_type="application/x-ndjson")
        return {"status": "success", "answer": cached_answer, "cached": True}

    logger.info("rag_query_started", query=request.query)
    
    # 2. Input Guardrail
    decision = evaluate_decision({"text": request.query})
    logger.info("guardrail_evaluated", jailbreak_prob=decision["answers"]["is_jailbreak"]["noul"])
    
    if decision["answers"]["is_jailbreak"]["noul"] > 0.8:
        logger.warning("request_blocked", reason="jailbreak_detected")
        return {"status": "blocked", "message": "Request flagged as malicious."}
    
    # 3. Retrieval
    context = retrieve_context(request.query, top_k=3)
    if not context:
        logger.info("no_context_found", query=request.query)
        return {"status": "no_context", "answer": "No relevant documents found."}
    
    # 4. Generation
    system_prompt = "You are an expert academic research assistant. Answer based ONLY on the context. Cite Page numbers."
    
    if request.stream:
        logger.info("streaming_response_started")
        return StreamingResponse(generate_stream(request.query, context, system_prompt), media_type="application/x-ndjson")
    
    answer = generate_with_fallback(system_prompt, f"Context:\n{context}\n\nQuestion: {request.query}")
    
    # 5. SAVE TO CACHE (Fixed deprecation warning: using set with ex= instead of setex)
    cache.set(cache_key, answer, ex=86400)
    
    logger.info("rag_query_success", routing=decision["answers"]["routing_category"]["choice"], answer_length=len(answer))
    return {"status": "success", "answer": answer, "routing": decision["answers"]["routing_category"]["choice"], "cached": False}

@app.post("/api/v1/ai/check-similarity")
async def check_similarity_endpoint(file: UploadFile = File(...)):
    try:
        logger.info("similarity_check_started", filename=file.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        check_similarity(tmp_path, threshold=0.85)
        os.unlink(tmp_path)
        logger.info("similarity_check_completed")
        return {"status": "success", "message": "Similarity check completed."}
    except Exception as e:
        logger.error("similarity_check_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/ai/extract-metadata")
async def extract_metadata_endpoint(file: UploadFile = File(...), doc_id: str = "unknown"):
    try:
        logger.info("metadata_extraction_started", doc_id=doc_id, filename=file.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        metadata = extract_metadata_from_pdf(tmp_path)
        save_metadata(doc_id, metadata)
        os.unlink(tmp_path)
        logger.info("metadata_extraction_completed", doc_id=doc_id)
        return {"status": "success", "metadata": metadata}
    except Exception as e:
        logger.error("metadata_extraction_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/ai/graphs")
async def get_graphs():
    logger.info("graphs_build_requested")
    build_and_print_graphs()
    return {"status": "success", "message": "Graphs built."}

if __name__ == "__main__":
    logger.info("server_starting", port=8000)
    uvicorn.run(app, host="0.0.0.0", port=8000)
# ==========================================
# RECOMMENDATION API ENDPOINTS (Section 7.8 & 13)
# ==========================================
from pydantic import BaseModel
from datetime import datetime

# Mock thesis metadata for the baseline engine (Replace with actual DB fetch in production)
MOCK_THESES_METADATA = [
    {"id": "thesis_1", "title": "Sample Thesis 1", "created_at": datetime.utcnow()},
    {"id": "thesis_2", "title": "Sample Thesis 2", "created_at": datetime.utcnow()},
    {"id": "thesis_3", "title": "Sample Thesis 3", "created_at": datetime.utcnow()},
]

# Initialize the Recommendation Service
rec_service = RecommendationService(theses=MOCK_THESES_METADATA)

class InteractionRequest(BaseModel):
    user_id: str
    thesis_id: str
    event_type: str  # Must be 'view', 'download', or 'save'

@app.post("/api/ai/interact")
async def log_interaction(req: InteractionRequest):
    """
    Section 7.8: Logs user interactions to build the dataset for the learned model.
    Call this from the frontend whenever a user views, downloads, or saves a thesis.
    """
    rec_service.logger_tool.log_event(req.user_id, req.thesis_id, req.event_type)
    return {"status": "success", "message": f"Logged {req.event_type} for thesis {req.thesis_id}"}

@app.get("/api/ai/recommend")
async def get_recommendations(user_id: str, top_k: int = 5):
    """
    Returns recommendations. Automatically uses the Learned Model if trained, 
    otherwise falls back to the Popularity/Recency Baseline.
    """
    recs = rec_service.get_recommendations(user_id, top_k)
    model_used = "learned_model" if rec_service.use_learned else "popularity_recency_baseline"
    return {"user_id": user_id, "recommendations": recs, "model_used": model_used}

@app.post("/api/ai/train-recommendation")
async def train_recommendation_model():
    """
    Section 13: Manually trigger training of the learned Matrix Factorization model.
    Call this once you have collected sufficient real interaction data (e.g., > 10 events).
    """
    interactions = rec_service.logger_tool.interactions
    if len(interactions) < 10:
        return {"status": "skipped", "message": f"Need at least 10 interactions to train. Currently have {len(interactions)}."}
    
    rec_service.train_on_data(interactions)
    return {"status": "success", "message": "Learned model trained successfully.", "interactions_used": len(interactions)}

# ==========================================
# RECOMMENDATION API ENDPOINTS (Section 7.8 & 13)
# ==========================================
from pydantic import BaseModel
from datetime import datetime

# Mock thesis metadata for the baseline engine (Replace with actual DB fetch in production)
MOCK_THESES_METADATA = [
    {"id": "thesis_1", "title": "Sample Thesis 1", "created_at": datetime.utcnow()},
    {"id": "thesis_2", "title": "Sample Thesis 2", "created_at": datetime.utcnow()},
    {"id": "thesis_3", "title": "Sample Thesis 3", "created_at": datetime.utcnow()},
]

# Initialize the Recommendation Service
rec_service = RecommendationService(theses=MOCK_THESES_METADATA)

class InteractionRequest(BaseModel):
    user_id: str
    thesis_id: str
    event_type: str  # Must be 'view', 'download', or 'save'

@app.post("/api/ai/interact")
async def log_interaction(req: InteractionRequest):
    """
    Section 7.8: Logs user interactions to build the dataset for the learned model.
    Call this from the frontend whenever a user views, downloads, or saves a thesis.
    """
    rec_service.logger_tool.log_event(req.user_id, req.thesis_id, req.event_type)
    return {"status": "success", "message": f"Logged {req.event_type} for thesis {req.thesis_id}"}

@app.get("/api/ai/recommend")
async def get_recommendations(user_id: str, top_k: int = 5):
    """
    Returns recommendations. Automatically uses the Learned Model if trained, 
    otherwise falls back to the Popularity/Recency Baseline.
    """
    recs = rec_service.get_recommendations(user_id, top_k)
    model_used = "learned_model" if rec_service.use_learned else "popularity_recency_baseline"
    return {"user_id": user_id, "recommendations": recs, "model_used": model_used}

@app.post("/api/ai/train-recommendation")
async def train_recommendation_model():
    """
    Section 13: Manually trigger training of the learned Matrix Factorization model.
    Call this once you have collected sufficient real interaction data (e.g., > 10 events).
    """
    interactions = rec_service.logger_tool.interactions
    if len(interactions) < 10:
        return {"status": "skipped", "message": f"Need at least 10 interactions to train. Currently have {len(interactions)}."}
    
    rec_service.train_on_data(interactions)
    return {"status": "success", "message": "Learned model trained successfully.", "interactions_used": len(interactions)}


# ==========================================
# NEW AI INTELLIGENCE ENDPOINTS (Sections 7.7, 7.8, 7.10)
# ==========================================
from pydantic import BaseModel
import numpy as np
from research_intelligence.gap_engine import GapEngine
from proposal_checker.service import ProposalChecker
from research_network.graph import ResearchNetworkGraph

# Initialize engines (Singleton pattern for the app lifecycle)
gap_engine = GapEngine()
network_graph = ResearchNetworkGraph()

# Mock embedding service for the API endpoint (Replace with your actual embeddings.service import in production)
class MockEmbeddingService:
    def embed_text(self, text: str):
        # Returns a dummy 384-dim vector for demonstration (all-MiniLM-L6-v2 dimension)
        return np.random.rand(384).astype(np.float32)

proposal_checker = ProposalChecker(embedding_service=MockEmbeddingService())

class ProposalCheckRequest(BaseModel):
    proposal_text: str
    threshold: float = 0.85

class AddEdgeRequest(BaseModel):
    researcher_a: str
    researcher_b: str
    basis_document_id: str
    basis_type: str = "co_authorship"

@app.get("/api/ai/detect-gaps")
async def detect_gaps():
    """
    Section 7.7 & 7.10: Triggers unsupervised research-gap detection using BERTopic.
    Uses synthetic data per Section 7.3 until real corpus is loaded.
    """
    mock_texts = [
        "Machine learning applications in African agricultural systems.",
        "Deep learning for medical imaging in resource-constrained settings.",
        "Machine learning applications in African agricultural systems." # Duplicate to force a low-count topic
    ]
    mock_ids = ["thesis_1", "thesis_2", "thesis_3"]
    
    gaps = gap_engine.detect_gaps(thesis_texts=mock_texts, thesis_ids=mock_ids)
    return {"status": "success", "gaps_detected": len(gaps), "gaps": gaps}

@app.post("/api/ai/check-proposal")
async def check_proposal(req: ProposalCheckRequest):
    """
    Section 7.10: Semantic similarity/plagiarism review engine.
    Checks new proposal text against existing corpus chunks.
    """
    # Mock corpus chunks (Replace with actual DB/Vector DB fetch in production)
    mock_chunks = [
        {
            "thesis_id": "thesis_1", 
            "id": "chunk_1", 
            "vector": np.random.rand(384).astype(np.float32), 
            "text": "This is a sample existing thesis text about machine learning in agriculture...", 
            "page": 12
        }
    ]
    
    flagged = proposal_checker.check_similarity(
        new_proposal_text=req.proposal_text, 
        existing_thesis_chunks=mock_chunks, 
        threshold=req.threshold
    )
    
    return {
        "status": "success", 
        "threshold_used": req.threshold,
        "flagged_chunks_count": len(flagged),
        "flagged_chunks": flagged
    }

@app.post("/api/ai/network/add-edge")
async def add_network_edge(req: AddEdgeRequest):
    """
    Section 7.8: Adds a provenance-required collaboration edge.
    Rejects the request if no basis_document_id is provided.
    """
    success = network_graph.add_provenance_edge(
        researcher_a=req.researcher_a,
        researcher_b=req.researcher_b,
        basis_document_id=req.basis_document_id,
        basis_type=req.basis_type
    )
    
    if success:
        return {"status": "success", "message": f"Provenance edge added between {req.researcher_a} and {req.researcher_b}."}
    else:
        return {"status": "error", "message": "Failed to add edge. Missing or invalid provenance basis."}

# ==========================================
# NEW AI INTELLIGENCE ENDPOINTS (Sections 7.7, 7.8, 7.10)
# ==========================================
from pydantic import BaseModel
import numpy as np
from research_intelligence.gap_engine import GapEngine
from proposal_checker.service import ProposalChecker
from research_network.graph import ResearchNetworkGraph

# Initialize engines (Singleton pattern for the app lifecycle)
gap_engine = GapEngine()
network_graph = ResearchNetworkGraph()

# Mock embedding service for the API endpoint (Replace with your actual embeddings.service import in production)
class MockEmbeddingService:
    def embed_text(self, text: str):
        # Returns a dummy 384-dim vector for demonstration (all-MiniLM-L6-v2 dimension)
        return np.random.rand(384).astype(np.float32)

proposal_checker = ProposalChecker(embedding_service=MockEmbeddingService())

class ProposalCheckRequest(BaseModel):
    proposal_text: str
    threshold: float = 0.85

class AddEdgeRequest(BaseModel):
    researcher_a: str
    researcher_b: str
    basis_document_id: str
    basis_type: str = "co_authorship"

@app.get("/api/ai/detect-gaps")
async def detect_gaps():
    """
    Section 7.7 & 7.10: Triggers unsupervised research-gap detection using BERTopic.
    Uses synthetic data per Section 7.3 until real corpus is loaded.
    """
    mock_texts = [
        "Machine learning applications in African agricultural systems.",
        "Deep learning for medical imaging in resource-constrained settings.",
        "Machine learning applications in African agricultural systems." # Duplicate to force a low-count topic
    ]
    mock_ids = ["thesis_1", "thesis_2", "thesis_3"]
    
    gaps = gap_engine.detect_gaps(thesis_texts=mock_texts, thesis_ids=mock_ids)
    return {"status": "success", "gaps_detected": len(gaps), "gaps": gaps}

@app.post("/api/ai/check-proposal")
async def check_proposal(req: ProposalCheckRequest):
    """
    Section 7.10: Semantic similarity/plagiarism review engine.
    Checks new proposal text against existing corpus chunks.
    """
    # Mock corpus chunks (Replace with actual DB/Vector DB fetch in production)
    mock_chunks = [
        {
            "thesis_id": "thesis_1", 
            "id": "chunk_1", 
            "vector": np.random.rand(384).astype(np.float32), 
            "text": "This is a sample existing thesis text about machine learning in agriculture...", 
            "page": 12
        }
    ]
    
    flagged = proposal_checker.check_similarity(
        new_proposal_text=req.proposal_text, 
        existing_thesis_chunks=mock_chunks, 
        threshold=req.threshold
    )
    
    return {
        "status": "success", 
        "threshold_used": req.threshold,
        "flagged_chunks_count": len(flagged),
        "flagged_chunks": flagged
    }

@app.post("/api/ai/network/add-edge")
async def add_network_edge(req: AddEdgeRequest):
    """
    Section 7.8: Adds a provenance-required collaboration edge.
    Rejects the request if no basis_document_id is provided.
    """
    success = network_graph.add_provenance_edge(
        researcher_a=req.researcher_a,
        researcher_b=req.researcher_b,
        basis_document_id=req.basis_document_id,
        basis_type=req.basis_type
    )
    
    if success:
        return {"status": "success", "message": f"Provenance edge added between {req.researcher_a} and {req.researcher_b}."}
    else:
        return {"status": "error", "message": "Failed to add edge. Missing or invalid provenance basis."}
