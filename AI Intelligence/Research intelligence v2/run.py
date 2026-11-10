"""Windows-friendly ASGI bootstrap for the V2 Research Intelligence service.

psycopg's async mode cannot run on Windows' default ProactorEventLoop. Uvicorn's
``run()`` creates/overrides the loop, so the policy set in ``oau_ai.db.session``
is too late. This bootstrap drives ``uvicorn.Server`` on an explicit
``SelectorEventLoop`` so psycopg works.

Usage:
    python run.py                 # binds 0.0.0.0:8888
    RI_HOST=127.0.0.1 RI_PORT=8001 python run.py
"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))


def main() -> None:
    import uvicorn

    config = uvicorn.Config(
        "oau_ai.main:app",
        host=os.getenv("RI_HOST", "0.0.0.0"),
        port=int(os.getenv("RI_PORT", "8888")),
        log_level="info",
        # Use asyncio event loop policy to avoid ProactorEventLoop on Windows,
        # which psycopg async cannot use.
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(server.serve())
    finally:
        pass


if __name__ == "__main__":
    main()
