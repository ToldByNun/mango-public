"""GPU backend detection for llama.cpp (CUDA, Vulkan, HIP)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mango_runtime.cuda_env import cuda_bin_dirs, ensure_cuda_on_path, list_ggml_backends

__all__ = [
    "cuda_bin_dirs",
    "detect_gpu_backend",
    "ensure_cuda_on_path",
    "gpu_install_hint",
    "has_backend_dll",
    "has_cuda_backend",
    "has_gpu_backend",
    "list_ggml_backends",
    "prepare_gpu_environment",
    "apply_backend_env",
    "backend_lib_dirs",
]


def backend_lib_dirs() -> list[Path]:
    """Directories that may contain ggml-*.dll / .so next to llama.cpp."""
    dirs: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path | None) -> None:
        if path is None or not path.is_dir():
            return
        key = str(path.resolve()).lower()
        if key in seen:
            return
        seen.add(key)
        dirs.append(path)

    try:
        from llama_cpp import llama_cpp
    except ImportError:
        llama_cpp = None  # type: ignore[assignment]

    if llama_cpp is not None:
        lib = getattr(llama_cpp, "_lib", None)
        lib_path = getattr(lib, "_name", None) if lib is not None else None
        if lib_path:
            _add(Path(lib_path).parent)
        pkg_file = getattr(llama_cpp, "__file__", None)
        if pkg_file:
            pkg_dir = Path(pkg_file).resolve().parent
            _add(pkg_dir / "lib")
            _add(pkg_dir)
            # Newer wheels also drop native libs under site-packages/bin.
            _add(pkg_dir.parent / "bin")

    for entry in sys.path:
        root = Path(entry)
        _add(root / "llama_cpp" / "lib")
        _add(root / "bin")

    return dirs


def _backend_libs_dir() -> Path | None:
    dirs = backend_lib_dirs()
    return dirs[0] if dirs else None


def has_backend_dll(name: str) -> bool:
    """True if ggml-<name>.dll/.so/.dylib exists in any llama.cpp lib dir."""
    needle = f"ggml-{name}"
    for root in backend_lib_dirs():
        for ext in (".dll", ".so", ".dylib"):
            if (root / f"{needle}{ext}").is_file():
                return True
    return False


# Back-compat alias used by older call sites / scripts.
_has_backend_dll = has_backend_dll


def detect_gpu_backend() -> str | None:
    """Pick the best GPU backend: CUDA > Vulkan > HIP."""
    names = [n.lower() for n in list_ggml_backends()]
    for preferred in ("cuda", "vulkan", "hip", "metal"):
        if any(preferred in name for name in names):
            return preferred
    for preferred in ("cuda", "vulkan", "hip"):
        if has_backend_dll(preferred):
            return preferred
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
    elif backend == "vulkan":
        # Ensure the llama.cpp lib dir (ggml-vulkan.dll) is searchable for deps.
        parts = os.environ.get("PATH", "").split(os.pathsep)
        lower = {p.lower() for p in parts}
        prepend: list[str] = []
        for directory in backend_lib_dirs():
            path = str(directory)
            if path.lower() not in lower:
                prepend.append(path)
        if prepend:
            os.environ["PATH"] = os.pathsep.join(prepend + parts)
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
        "Install a GPU wheel: pip install llama-cpp-python --force-reinstall "
        "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/vulkan "
        "(AMD/Intel) or .../whl/cu124 (NVIDIA). "
        "Or run runtime/scripts/install_llama_cpp_vulkan.bat"
    )
