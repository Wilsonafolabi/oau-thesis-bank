# OAU Thesis Bank — Phase 3 Research Intelligence (V2)

This is the V2 implementation of the AI Intelligence Layer, built in
`AI Intelligence/Research intelligence v2/` as a fresh, independent service.
The existing `Research intelligence/` directory (V1) is used as a read-only
reference only; this directory does not modify it, the Phase 2 Django backend,
or the Phase 2 React frontend.

## Design decisions (fixed)

- **DeepSeek** is the primary reasoning/generation provider.
- **Groq** handles explicitly designated smaller tasks only. It is not a
  fallback for DeepSeek and must not silently take over primary-model tasks.
- **No automatic provider fallback.** Provider failure returns a structured
  error; it never silently switches to another model.
- **Cloudflare Vectorize** is the vector index for thesis chunk embeddings and
  retrieval metadata.
- **JEV** retains its complete decision-making, workflow, and security scope.
- **Django remains the authority** for authentication, roles, thesis
  permissions, and access to private thesis content. The AI service never
  trusts browser-supplied roles or user IDs.

## Source layout

```
src/oau_ai/           # implementation package
tests/                # pytest suite
pyproject.toml        # project metadata and dev dependencies
.env.example          # environment variable template (no secrets)
```

## Setup

```powershell
cd "AI Intelligence\Research intelligence v2"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
# Edit .env with real values (never commit real secrets)
```

## Tests

```powershell
pytest
```

## Contract

See `PHASE_3_IMPLEMENTATION_CONTRACT.md` in this directory for the V2 amended
Phase 3 contract, including the model-routing section reflecting the decisions
above.
