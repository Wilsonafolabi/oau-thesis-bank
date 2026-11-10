"""Shared synchronization and CUDA cleanup for local inference models."""

from __future__ import annotations

import threading

MODEL_RUNTIME_LOCK = threading.RLock()


def clear_cuda_cache() -> None:
    try:
        import torch

        torch.cuda.empty_cache()
    except Exception:
        pass