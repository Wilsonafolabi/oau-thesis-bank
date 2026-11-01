"""Researcher Memory System — Phase 5.3.

Provides persistent, user-specific memory across conversations with four
layers:
- Working memory (rolling window of exchanges)
- Researcher profile memory (stable research context)
- Research and document memory (thesis summaries)
- Semantic and entity memory (entities + relationships + Vectorize)

All memories are scoped to their owner user_id. PostgreSQL is the canonical
store; Cloudflare Vectorize is used only for semantic retrieval with
user_id-based isolation.
"""

from .service import MemoryService, MemoryEntry, MemorySearchResult

__all__ = ["MemoryService", "MemoryEntry", "MemorySearchResult"]
