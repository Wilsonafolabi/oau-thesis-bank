import asyncio
import selectors
import uvicorn

asyncio.set_event_loop_policy(
    asyncio.WindowsSelectorEventLoopPolicy()
)

if __name__ == "__main__":
    uvicorn.run(
        "oau_ai.main:app",
        host="127.0.0.1",
        port=8888,
        reload=False
    )
