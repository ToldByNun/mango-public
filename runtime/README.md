# Runtime

Minimal GGUF model runner — backed by [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) (llama.cpp).

## GPU (CUDA)

The PyPI default wheel is **CPU-only**. For an NVIDIA GPU you must rebuild with CUDA:

```powershell
# Developer Command Prompt / vcvars64. Visual Studio often has no CUDA toolset —
# use Ninja so nvcc is invoked directly:
$env:CUDA_PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3"
$env:PATH = "$env:CUDA_PATH\bin\x64;$env:CUDA_PATH\bin;$env:PATH"
$env:CMAKE_GENERATOR = "Ninja"
$env:CMAKE_ARGS = "-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=120 -DGGML_CCACHE=OFF"  # 120 = RTX 50
$env:FORCE_CMAKE = "1"
pip install llama-cpp-python --force-reinstall --no-cache-dir
```

Helper script: `runtime/scripts/install_llama_cpp_cuda.bat` (set `PIP` to the target venv pip).

Set `hardware.n_gpu_layers: -1` in `config.yaml` to offload all layers. `0` keeps inference on CPU.

On load, the runner prepends the CUDA `bin` / `bin\x64` folders to `PATH` (needed for `cublas64_13.dll` on CUDA 13) and refuses GPU offload if the installed `llama-cpp-python` has no CUDA backend.

## Setup

```powershell
cd runtime/python
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Configuration

| Key | Meaning |
|-----|---------|
| `model.path` | Path to `.gguf` file |
| `model.n_ctx` | Context window (tokens) |
| `hardware.n_gpu_layers` | `0` = CPU, `-1` = all layers on GPU |
| `hardware.n_threads` | CPU threads (`0` = auto) |
| `inference.*` | Default sampling parameters |

Environment overrides:

- `MANGO_GGUF_MODEL_PATH` — overrides `model.path`
- `MANGO_RUNTIME_CONFIG` — path to alternate config

## Usage

```python
from mango_runtime import ModelRunner

with ModelRunner() as runner:
    result = runner.complete("Hello!")
    print(result.text)
    # Lazy GBNF: free text until trigger, then constrain the tool-call tail.
    # result = runner.complete(prompt, grammar=gbnf, grammar_trigger="<tool_call=")
    # reset_cache=False keeps the KV prefix (do not wipe between thought and tool).
```

```powershell
python -m mango_runtime "Your prompt here"
```
