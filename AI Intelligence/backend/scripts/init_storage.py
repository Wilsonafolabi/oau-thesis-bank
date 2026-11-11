"""Create the configured object storage bucket for the Docker dev stack."""

import os
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError


client = boto3.client(
    "s3",
    endpoint_url=os.environ["STORAGE_ENDPOINT_URL"],
    aws_access_key_id=os.environ["STORAGE_ACCESS_KEY"],
    aws_secret_access_key=os.environ["STORAGE_SECRET_KEY"],
    region_name=os.environ.get("STORAGE_REGION") or "us-east-1",
)
bucket = os.environ["STORAGE_BUCKET_NAME"]

for attempt in range(1, 13):
    try:
        existing = {item["Name"] for item in client.list_buckets().get("Buckets", [])}
        if bucket not in existing:
            client.create_bucket(Bucket=bucket)
        print(f"Storage bucket ready: {bucket}")
        break
    except (BotoCoreError, ClientError) as error:
        if attempt == 12:
            raise
        print(f"Storage is not ready yet ({error}); retrying in 5 seconds")
        time.sleep(5)
