import os, httpx, logging
from typing import Dict, Any
from decision_layer.schemas import TaskType

logger = logging.getLogger(__name__)

class JEVClient:
    def __init__(self, base_url: str = "https://api.typesafe.ai/v1", timeout: float = 2.0):
        self.api_key = os.getenv("JEV_API_KEY")
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=timeout)
        self.is_available = bool(self.api_key)

    async def classify(self, state: Dict[str, Any], questions: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_available:
            return {"status": "unavailable", "reason": "missing_api_key"}
        
        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            response = await self.client.post(f"{self.base_url}/systemone", json={"state": state, "questions": questions}, headers=headers)
            response.raise_for_status()
            return {"status": "success", "data": response.json()}
        except httpx.TimeoutException:
            return {"status": "error", "reason": "timeout"}
        except Exception as e:
            return {"status": "error", "reason": str(e)}
