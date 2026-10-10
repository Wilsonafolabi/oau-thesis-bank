# AI Intelligence Service - Integration Contract

## Service Boundary
The AI Intelligence service is an independently deployable microservice. 
It DOES NOT own user records, authentication, or the primary thesis metadata. 
It relies on the Core Backend to authenticate users and upload files to Object Storage (MinIO/S3).

## API Contract (Backend -> AI Service)
The backend must call the AI service with a valid internal service token.

### 1. Ingest Document
`POST /api/v1/ai/documents/ingest`
Headers: `X-Internal-Service-Token: <shared_secret>`
Body:
{
  "backend_thesis_id": "uuid-from-backend",
  "backend_user_id": "uuid-from-backend",
  "object_key": "theses/uuid-from-backend.pdf",
  "access_level": "private"
}

### 2. Job Status
`GET /api/v1/ai/jobs/{job_id}`

### 3. Delete Document (Triggers cascade cleanup of chunks/index)
`DELETE /api/v1/ai/documents/{backend_thesis_id}`

## Database Ownership
- **Core Backend Owns:** `users`, `theses`, `departments`, `permissions`.
- **AI Service Owns:** `ai_intelligence.ai_documents`, `ai_intelligence.ai_jobs`, `ai_intelligence.ai_chunks`.
