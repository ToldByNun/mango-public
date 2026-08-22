"""GPU backend detection for llama.cpp (CUDA, Vulkan, HIP)."""

from __future__ import annotations

import os
from pathlib import Path

from mango_runtime.cuda_env import cuda_bin_dirs, ensure_cuda_on_path, list_ggml_backends

__all__ = [
    "cuda_bin_dirs",
    "detect_gpu_backend",
    "ensure_cuda_on_path",
    "gpu_install_hint",
    "has_cuda_backend",
    "has_gpu_backend",
    "list_ggml_backends",
    "prepare_gpu_environment",
    "apply_backend_env",
]


def _backend_libs_dir() -> Path | None:
    try:
        from llama_cpp import llama_cpp
    except ImportError:
        return None
    lib = getattr(llama_cpp, "_lib", None)
    lib_path = getattr(lib, "_name", None) if lib is not None else None
    if not lib_path:
        return None
    return Path(lib_path).parent


def _has_backend_dll(name: str) -> bool:
    root = _backend_libs_dir()
    if root is None:
        return False
    for ext in (".dll", ".so", ".dylib"):
        if (root / f"ggml-{name}{ext}").is_file():
            return True
    return False


def detect_gpu_backend() -> str | None:
    """Pick the best GPU backend: CUDA > Vulkan > HIP."""
    names = [n.lower() for n in list_ggml_backends()]
    for preferred in ("cuda", "vulkan", "hip", "metal"):
        if any(preferred in name for name in names):
            return preferred
    if _has_backend_dll("cuda"):
        return "cuda"
    if _has_backend_dll("vulkan"):
        return "vulkan"
    if _has_backend_dll("hip"):
        return "hip"
    return None


def has_gpu_backend() -> bool:
    return detect_gpu_backend() is not None


def has_cuda_backend() -> bool:
    return detect_gpu_backend() == "cuda"


def prepare_gpu_environment() -> str | None:
    """Set PATH / env vars for the active GPU backend. Returns backend name or None."""
    backend = detect_gpu_backend()
    if backend == "cuda":
        ensure_cuda_on_path()
    return backend


def apply_backend_env(backend: str | None) -> None:
    """Backend-specific runtime env (CUDA graphs off only for CUDA)."""
    if backend != "cuda":
        return
    os.environ.setdefault("GGML_CUDA_ENABLE_GRAPHS", "0")
    os.environ.setdefault("GGML_CUDA_DISABLE_GRAPHS", "1")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    os.environ.setdefault("GGML_CUDA_ENABLE_UNIFIED_MEMORY", "0")


def gpu_install_hint() -> str:
    return (
        "Install a GPU wheel: pip install llama-cpp-python "
        "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/vulkan "
        "(AMD/Intel) or .../whl/cu124 (NVIDIA)."
    )
