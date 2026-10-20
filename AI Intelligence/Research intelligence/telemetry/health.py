from typing import Dict, Any, Callable, Awaitable
import asyncio

class HealthCheckManager:
    def __init__(self):
        self._app_healthy = True
        self._dependencies: Dict[str, Callable[[], Awaitable[bool]]] = {}

    def register_dependency(self, name: str, check_fn: Callable[[], Awaitable[bool]]):
        self._dependencies[name] = check_fn

    def set_app_unhealthy(self):
        self._app_healthy = False

    async def check_health(self) -> Dict[str, Any]:
        # 1. Application Health (Internal state)
        app_status = "healthy" if self._app_healthy else "degraded"
        
        # 2. Dependency Health (External services)
        dep_results = {}
        for name, fn in self._dependencies.items():
            try:
                is_up = await asyncio.wait_for(fn(), timeout=2.0)
                dep_results[name] = "healthy" if is_up else "unhealthy"
            except Exception:
                dep_results[name] = "unreachable"

        # Overall readiness requires app to be healthy AND all critical deps to be healthy
        all_deps_healthy = all(v == "healthy" for v in dep_results.values())
        readiness = "ready" if (self._app_healthy and all_deps_healthy) else "not_ready"

        return {
            "status": app_status,
            "readiness": readiness,
            "dependencies": dep_results
        }

health_manager = HealthCheckManager()
