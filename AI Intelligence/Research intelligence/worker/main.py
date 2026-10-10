import asyncio, json, logging, os
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.session import AsyncSessionLocal
from db.models import AIJob, JobStatus, AIDocument
from storage.object_store import ObjectStore

logger = logging.getLogger(__name__)

async def process_job(job_id: str, db: AsyncSession):
    result = await db.execute(select(AIJob).where(AIJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job: return

    if job.status == JobStatus.SUCCESS: return # Idempotent

    if job.attempts >= job.max_attempts:
        job.status = JobStatus.FAILED
        job.error_message = "Max attempts exceeded"
        await db.commit()
        return

    job.status = JobStatus.PROCESSING
    job.attempts += 1
    await db.commit()

    try:
        doc_result = await db.execute(select(AIDocument).where(AIDocument.id == job.document_id))
        doc = doc_result.scalar_one()
        
        store = ObjectStore()
        local_path = await store.download(doc.object_key)
        
        # Note: Pipeline needs to be adapted to accept an AsyncSession. 
        # For this boundary, we simulate the processing step.
        logger.info(f"Processing {doc.object_key}...")
        await asyncio.sleep(1) # Simulate work
        
        job.status = JobStatus.SUCCESS
        await db.commit()
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        job.error_message = str(e)[:500]
        job.status = JobStatus.PENDING if job.attempts < job.max_attempts else JobStatus.FAILED
        await db.commit()

async def worker_loop(redis_url: str):
    r = aioredis.from_url(redis_url, decode_responses=True)
    logger.info("Worker started, polling Redis...")
    while True:
        try:
            result = await r.brpop("ai_intelligence:jobs", timeout=5)
            if not result: continue
            _, job_json = result
            data = json.loads(job_json)
            async with AsyncSessionLocal() as db:
                await process_job(data["job_id"], db)
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(worker_loop(os.getenv("REDIS_URL", "redis://localhost:6379/0")))
