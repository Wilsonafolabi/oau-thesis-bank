from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.routes import router as v1_router

app = FastAPI(
    title="OAU Thesis Bank - Phase 3 API",
    description="Integrated AI Intelligence backend with JEV/Laya routing, NeMo Guardrails, and Researcher Intelligence.",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)

@app.get("/")
def root():
    return {"message": "OAU Thesis Bank API is running.", "docs": "/docs"}

# --- Mount legacy Phase 3 AI routers (real services from api/routes.py) ---
try:
    from api.routes import router as legacy_ai_router
    if getattr(legacy_ai_router, "prefix", "") in ("", "/"):
        app.include_router(legacy_ai_router, prefix="/api/ai")
    else:
        app.include_router(legacy_ai_router)
    print("[startup] Legacy AI router mounted (/api/ai/*)")
except Exception as e:
    print(f"[startup] Legacy AI router NOT available (dependency missing): {e}")
