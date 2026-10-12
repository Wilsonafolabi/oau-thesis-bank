from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from pydantic import BaseModel
from db.session import get_async_session
from plagiarism_detection.detector import PlagiarismDetector

router = APIRouter()

class PlagiarismCheckRequest(BaseModel):
    text: str
    exclude_document_ids: List[str] = []

@router.post("/api/v1/plagiarism/check")
async def check_plagiarism(
    request: PlagiarismCheckRequest,
    user_id: str = Header(...),
    access_levels: str = Header(default="public"),
    db: AsyncSession = Depends(get_async_session)
):
    """Check submitted text for potential plagiarism."""
    
    # Validate input size
    if len(request.text) > 50000:  # 50KB limit
        raise HTTPException(status_code=413, detail="Text too large. Maximum 50,000 characters.")
    
    if len(request.text.strip()) < 100:
        raise HTTPException(status_code=400, detail="Text too short. Minimum 100 characters.")
    
    # Parse access levels
    access_list = [level.strip() for level in access_levels.split(",")]
    
    # Run detection
    detector = PlagiarismDetector()
    result = await detector.detect_similarity(
        db=db,
        submitted_text=request.text,
        user_id=user_id,
        access_levels=access_list,
        exclude_document_ids=request.exclude_document_ids
    )
    
    return result
