import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class LayaClient:
    """Local System One fallback using convaiinnovations/laya."""
    def __init__(self, local_dir: Optional[str] = None):
        self.local_dir = local_dir
        self._router = None

    def _get_router(self):
        if self._router is None:
            try:
                import laya
                if self.local_dir:
                    # Use laya.load() for local directories
                    logger.info(f"Loading Laya from local snapshot: {self.local_dir}")
                    self._router = laya.load(self.local_dir)
                else:
                    # Use Router for default cache behavior
                    from laya import Router
                    logger.info("Loading Laya Router...")
                    self._router = Router()
            except Exception as e:
                logger.error(f"Laya failed to load: {e}")
                raise
        return self._router

    def predict(self, state: Dict[str, Any], questions: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous local prediction (~33ms)."""
        router = self._get_router()
        # Both Router and Agent (from laya.load) have a .predict method
        return router.predict(state, questions)
