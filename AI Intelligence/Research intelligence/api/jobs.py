import uuid
from typing import Dict, Optional, Any
from api.schemas import JobStatus, JobResponse

# In-memory job store for scaffold. In production, replace with Redis/DB.
_jobs: Dict[str, Dict[str, Any]] = {}

def create_job(task_name: str) -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "task": task_name,
        "status": JobStatus.PROCESSING,
        "message": f"Started {task_name}",
        "result": None
    }
    return job_id

def update_job(job_id: str, status: JobStatus, result: Optional[Dict] = None, message: str = ""):
    if job_id in _jobs:
        _jobs[job_id]["status"] = status
        _jobs[job_id]["result"] = result
        _jobs[job_id]["message"] = message

def get_job(job_id: str) -> Optional[JobResponse]:
    job = _jobs.get(job_id)
    if not job:
        return None
    return JobResponse(**job)
