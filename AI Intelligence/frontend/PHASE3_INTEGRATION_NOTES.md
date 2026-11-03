# Phase 3 integration patch — OAU Thesis Bank

## Applied changes
- AI service base URL now reads `VITE_AI_API_BASE_URL` instead of hard-coding localhost in source.
- `.env.example` now points to `http://127.0.0.1:8888/api`, matching the client paths (`v1/...`). The former `/api/ai` suffix would have produced mismatched URLs unless the server explicitly mounts routes there.
- AI assistant displays returned citations, decision engine, and confidence when the backend provides them. It does not fabricate these values.

## Run frontend
1. Extract this archive.
2. Open PowerShell in the `frontend` folder.
3. `Copy-Item .env.example .env.local` (edit host URLs if your services run elsewhere).
4. `npm install`
5. `npm run build`
6. `npm run dev`

## Local service defaults
- Django/repository API: `http://127.0.0.1:8000/api`
- FastAPI AI service: `http://127.0.0.1:8888/api`

These are defaults, not proof that services are running. Start the existing backend and AI service separately. Do not reset Docker volumes or the Phase 2 database.

## Integration boundary to verify against the live backend
The frontend calls `v1/rag/ask`, `v1/documents/upload`, `v1/documents/jobs/{job_id}`, `v1/research-gaps`, `v1/intelligence/researchers`, `v1/evaluations/status`, and `v1/health`. The uploaded `build_docdm_data.py` is a dataset builder that calls Ollama; it does not define these HTTP routes. The FastAPI Phase 3 backend source was not included in the uploaded archive, so this patch does not claim those endpoints are all live.

## Known implementation caveats from the supplied frontend
- `checkSimilarity` queues an upload and returns a processing message; it does not poll the job status yet.
- `summarizeThesis`, `checkProposal`, and `extendIdea` currently send natural-language prompts to the RAG endpoint rather than dedicated task endpoints. This is only correct if the backend intentionally supports those request semantics.
- `getRecommendations` currently calls the researcher-list endpoint; it should not be presented as thesis recommendations until the API contract is corrected.
- UI role checks are convenience only. Authorization must remain enforced by the backend.
