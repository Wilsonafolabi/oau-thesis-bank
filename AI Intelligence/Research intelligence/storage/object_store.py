import os
import boto3
from botocore.config import Config
from pathlib import Path

class ObjectStore:
    def __init__(self):
        self.client = boto3.client(
            's3',
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT", "http://localhost:9000"),
            aws_access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_KEY", "minioadmin"),
            config=Config(signature_version='s3v4'),
            region_name=os.getenv("OBJECT_STORAGE_REGION", "auto")
        )
        self.bucket = os.getenv("OBJECT_STORAGE_BUCKET_DOCUMENTS", "oau-thesis-documents")
        self.temp_dir = Path("temp_downloads")
        self.temp_dir.mkdir(exist_ok=True)

    async def download(self, object_key: str) -> str:
        local_path = self.temp_dir / object_key.replace("/", "_")
        # In production, use async boto3 (aioboto3). Using sync here for simplicity.
        self.client.download_file(self.bucket, object_key, str(local_path))
        return str(local_path)
