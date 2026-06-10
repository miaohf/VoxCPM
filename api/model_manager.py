from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

import torch
import voxcpm

from api.config import get_allowed_models
from api.errors import api_error

_MODEL_CACHE: dict[str, voxcpm.VoxCPM] = {}
_MODEL_CACHE_LOCK = Lock()
_GENERATION_LOCK = Lock()


def validate_model_id(model_id: str) -> str:
    model_id = (model_id or "").strip()
    allowed_models = get_allowed_models()
    if model_id not in allowed_models:
        raise api_error(
            400,
            "MODEL_NOT_ALLOWED",
            f"`model` '{model_id}' is not allowed. Allowed models: {', '.join(allowed_models)}.",
        )
    return model_id


def get_model(model_id: str) -> voxcpm.VoxCPM:
    model_id = validate_model_id(model_id)
    with _MODEL_CACHE_LOCK:
        model = _MODEL_CACHE.get(model_id)
        if model is None:
            model = voxcpm.VoxCPM.from_pretrained(model_id, optimize=True)
            _MODEL_CACHE[model_id] = model
        return model


@contextmanager
def generation_lock() -> Iterator[None]:
    with _GENERATION_LOCK:
        yield


def clear_cuda_cache() -> None:
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
