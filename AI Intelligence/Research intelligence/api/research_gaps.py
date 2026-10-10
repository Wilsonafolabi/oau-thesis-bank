from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_async_session
from research_gap_engine.engine import ResearchGapEngine
from security.nemoguardrails.runtime import get_runtime
from security.nemoguardrails.schemas import GuardrailsRequest, GuardrailOutcome

router = APIRouter()

@router.post("/api/v1/research/gaps")
async def analyze_research_gaps(
    query: str,
    user_id: str = Header(...),
    access_levels: str = Header(default="public"),
    db: AsyncSession = Depends(get_async_session)
):
    """Analyze research gaps for a given query."""
    
    # Input guardrails
    guardrails = get_runtime()
    guardrails_req = GuardrailsRequest(
        request_id=f"gap_{hash(query)}",
        user_input=query,
        evidence=[]
    )
    guardrails_resp = await guardrails.run(guardrails_req)
    
    if guardrails_resp.outcome == GuardrailOutcome.BLOCKED:
        raise HTTPException(status_code=400, detail="Query blocked by safety policies")
    
    # Parse access levels
    access_list = [level.strip() for level in access_levels.split(",")]
    
    # Run gap analysis
    engine = ResearchGapEngine()
    result = await engine.analyze_research_gaps(
        db=db,
        query=query,
        user_id=user_id,
        access_levels=access_list
    )
    
    return result
