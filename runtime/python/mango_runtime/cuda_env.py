from __future__ import annotations

import os
from pathlib import Path


def cuda_bin_dirs() -> list[Path]:
    """Return CUDA bin directories that must be on PATH for cuBLAS (CUDA 13 uses bin/x64)."""
    candidates: list[Path] = []
    env_path = os.environ.get("CUDA_PATH") or os.environ.get("CUDA_HOME")
    if env_path:
        candidates.append(Path(env_path))

    toolkit = Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA")
    if toolkit.is_dir():
        versions = sorted(
            [p for p in toolkit.iterdir() if p.is_dir() and p.name.startswith("v")],
            reverse=True,
        )
        candidates.extend(versions)

    dirs: list[Path] = []
    seen: set[str] = set()
    for root in candidates:
        for sub in (root / "bin" / "x64", root / "bin"):
            if not sub.is_dir():
                continue
            key = str(sub).lower()
            if key in seen:
                continue
            seen.add(key)
            dirs.append(sub)
    return dirs


def ensure_cuda_on_path() -> list[str]:
    """Prepend CUDA bin dirs so llama.cpp can load cublas64_*.dll at runtime."""
    added: list[str] = []
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep)
    lower = {p.lower() for p in parts}
    prepend: list[str] = []
    for directory in cuda_bin_dirs():
        path = str(directory)
        if path.lower() not in lower:
            prepend.append(path)
            added.append(path)
    if prepend:
        os.environ["PATH"] = os.pathsep.join(prepend + parts)
    if not os.environ.get("CUDA_PATH"):
        bins = cuda_bin_dirs()
        if bins:
            first = bins[0]
            root = first.parent.parent if first.name.lower() == "x64" else first.parent
            os.environ["CUDA_PATH"] = str(root)
    return added


def list_ggml_backends() -> list[str]:
    """Return registered llama.cpp backends (CPU, CUDA, ...)."""
    try:
        from llama_cpp import llama_cpp
    except ImportError:
        return []
    names: list[str] = []
    count_fn = getattr(llama_cpp, "ggml_backend_reg_count", None)
    get_fn = getattr(llama_cpp, "ggml_backend_reg_get", None)
    name_fn = getattr(llama_cpp, "ggml_backend_reg_name", None)
    if not (count_fn and get_fn and name_fn):
        return names
    for i in range(int(count_fn())):
        reg = get_fn(i)
        raw = name_fn(reg)
        names.append(raw.decode() if isinstance(raw, bytes) else str(raw))
    return names


def has_cuda_backend() -> bool:
    if any("cuda" in name.lower() for name in list_ggml_backends()):
        return True
    try:
        from llama_cpp import llama_cpp
    except ImportError:
        return False
    lib = getattr(llama_cpp, "_lib", None)
    lib_path = getattr(lib, "_name", None) if lib is not None else None
    if not lib_path:
        return False
    return (Path(lib_path).parent / "ggml-cuda.dll").is_file() or (
        Path(lib_path).parent / "ggml-cuda.so"
    ).is_file()
