"""Runtime config for local GGUF inference (llama.cpp)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_ENV_PATH = _BACKEND_ROOT / ".env"
load_dotenv(_ENV_PATH)
load_dotenv()

DEFAULT_MODEL_FILENAME = "Qwen3-4B-Q4_K_M.gguf"
DEFAULT_MODELS_DIR = _BACKEND_ROOT / "models"


def _default_model_path() -> Path:
    return DEFAULT_MODELS_DIR / DEFAULT_MODEL_FILENAME


@dataclass(frozen=True)
class AIConfig:
    model_path: Path
    temperature: float
    max_tokens: int
    n_ctx: int
    n_threads: int
    n_gpu_layers: int

    @property
    def model(self) -> str:
        return self.model_path.name

    @property
    def configured(self) -> bool:
        return self.model_path.is_file()


def get_ai_config() -> AIConfig:
    raw_path = (os.getenv("LOCAL_MODEL_PATH") or "").strip()
    if raw_path:
        model_path = Path(raw_path).expanduser()
        if not model_path.is_absolute():
            model_path = (_BACKEND_ROOT / model_path).resolve()
        else:
            model_path = model_path.resolve()
    else:
        model_path = _default_model_path()

    threads_env = os.getenv("LOCAL_N_THREADS", "").strip()
    if threads_env:
        n_threads = max(1, int(threads_env))
    else:
        n_threads = max(1, (os.cpu_count() or 4) - 1)

    return AIConfig(
        model_path=model_path,
        temperature=float(os.getenv("AI_TEMPERATURE", "0.3")),
        max_tokens=int(os.getenv("AI_MAX_TOKENS", "3072")),
        n_ctx=int(os.getenv("LOCAL_N_CTX", "4096")),
        n_threads=n_threads,
        n_gpu_layers=int(os.getenv("LOCAL_N_GPU_LAYERS", "0")),
    )
