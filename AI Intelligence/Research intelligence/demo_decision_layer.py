import asyncio
import os
from decision_layer.router import TypedDecisionRouter
from decision_layer.schemas import FallbackEngine

# TODO: Replace this with the actual path to your existing Laya download!
# Example: r"C:\Users\Administrator\.cache\huggingface\hub\models--convaiinnovations--laya\snapshots\..."
# Or wherever you manually downloaded the convaiinnovations/laya files.
LOCAL_LAYA_PATH = r"C:\Users\Administrator\.cache\huggingface\hub\models--convaiinnovations--laya\snapshots\55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851" # Set this to your path, e.g., r"C:\my_models\laya"

async def main():
    print("="*60)
    print("DECISION LAYER LIVE DEMO")
    print("="*60)
    
    # Initialize router with your local Laya path (if provided)
    from decision_layer.laya_client import LayaClient
    local_laya = LayaClient(local_dir=LOCAL_LAYA_PATH)
    
    router = TypedDecisionRouter()
    router.laya = local_laya # Inject the locally-configured client
    
    print("\nScenario: JEV API key is missing -> Falling back to local Laya")
    if LOCAL_LAYA_PATH:
        print(f"Using existing local Laya at: {LOCAL_LAYA_PATH}")
    else:
        print("No local path provided. Hugging Face will download to cache if missing.")
    print("-" * 60)
    
    result = await router.route(
        task_type="content_moderation",
        state={"text": "This is a safe message"},
        user_id="demo_user"
    )
    
    print(f"\n✅ Success!")
    print(f"Engine Used:      {result.engine_used.value}")
    print(f"Fallback Reason:  {result.fallback_reason.value}")
    print(f"Decision:         {result.decision.value}")
    print(f"Confidence:       {result.confidence:.2%}")
    print(f"Raw Answer:       {result.provenance.get('raw_answers', {})}")

if __name__ == "__main__":
    asyncio.run(main())

