import json, time, redis, structlog
from .pipeline import DocumentProcessingPipeline

logger = structlog.get_logger()

class DocumentWorker:
    def __init__(self, redis_url: str, db_dsn: str):
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.queue_name = "oau:document_processing:queue"
        self.pipeline = DocumentProcessingPipeline(db_dsn)

    def run(self):
        logger.info("worker_started", queue=self.queue_name)
        while True:
            try:
                result = self.redis_client.brpop(self.queue_name, timeout=2)
                if not result: continue
                _, job_json = result
                job = json.loads(job_json)
                job_id = job["job_id"]
                
                if self.redis_client.sismember("oau:processed_jobs", job_id):
                    continue
                    
                self.redis_client.set(f"oau:job_status:{job_id}", "processing")
                self.pipeline.process(job_id, job["document_id"], job["file_path"], job.get("metadata"))
                self.redis_client.sadd("oau:processed_jobs", job_id)
                self.redis_client.set(f"oau:job_status:{job_id}", "success")
            except redis.exceptions.ConnectionError:
                logger.error("redis_connection_lost", retry_in=2)
                time.sleep(2)
            except Exception as e:
                logger.error("worker_job_failed", error=str(e))
                if 'job_id' in locals():
                    self.redis_client.set(f"oau:job_status:{job_id}", f"failed:{str(e)}")