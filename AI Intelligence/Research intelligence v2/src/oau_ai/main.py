"""FastAPI application entry point for Phase 3 V2.

The V2 AI Intelligence service is an independently deployable microservice.
It does NOT own user records, authentication, or primary thesis metadata.
It relies on Django (Phase 2 backend) for authentication and authorization.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .db.session import close_database_connection


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from .db.session import init_db

    # Create the ai_intelligence schema and tables if missing. Idempotent.
    await init_db()
    yield
    await close_database_connection()


app = FastAPI(
    title="OAU Thesis Bank — Phase 3 AI Intelligence (V2)",
    description=(
        "AI Intelligence Layer for the OAU Thesis Bank. "
        "DeepSeek is the primary reasoning/generation provider. "
        "Groq is reserved for explicitly designated smaller tasks only. "
        "No automatic provider fallback. "
        "Cloudflare Vectorize is the vector index. "
        "Django remains the authority for authentication and authorization."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

# CORS — restrict to configured origins in production.
# Default: allow only localhost for development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/")
def root():
    return {
        "message": "OAU Thesis Bank Phase 3 AI Intelligence (V2) is running.",
        "docs": "/docs",
        "primary_provider": "deepseek",
        "vectorize": "cloudflare",
    }
