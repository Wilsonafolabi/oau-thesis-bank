# OAU Thesis Bank — Connected Frontend

The React frontend keeps the existing Phase 2 API integration and now routes
all AI features through a single configurable AI service URL.

## URLs

- Phase 2 backend: `VITE_API_BASE_URL` (default `http://127.0.0.1:8000/api`)
- AI Intelligence: `VITE_AI_API_BASE_URL` (default `http://127.0.0.1:8888/api/ai`)

Copy `.env.example` to `.env.local`.

## AI screens now connected

- Thesis AI summary
- Research idea similarity
- Similarity evidence results
- Idea extension
- Research gap explorer/detail
- RAG research assistant
- RAG answers with retrieved sources

The Phase 2-dependent screens still require the existing Django backend because
that backend was not part of the uploaded archive.
