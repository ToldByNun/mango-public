# Runtime

Minimal GGUF model runner — backed by [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) (llama.cpp).

## Warum llama-cpp-python?

| Option | Pro | Contra |
|--------|-----|--------|
| **llama-cpp-python** | Native API, Streaming, KV-Cache, GPU-Wheels | Python-Abhängigkeit |
| llama-cli Subprocess | Kein Binding nötig | IPC-Overhead, schlechtes Streaming |
| Direktes C++ llama.cpp | Max. Performance | Bindings-Aufwand (später) |

Für Phase 1 ist **llama-cpp-python** die beste Balance: isoliert lauffähig und später per C++-Kern ersetzbar, ohne die Python-API zu brechen.

## Setup

```powershell
cd runtime/python
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

GPU (CUDA-Beispiel):

```powershell
$env:CMAKE_ARGS = "-DGGML_CUDA=on"
pip install --force-reinstall llama-cpp-python
```

## Konfiguration

```powershell
copy ..\config.example.yaml ..\config.yaml
# model.path und hardware.n_gpu_layers anpassen
```

| Key | Bedeutung |
|-----|-----------|
| `model.path` | Pfad zur `.gguf`-Datei |
| `model.n_ctx` | Kontext-Fenster (Tokens) |
| `hardware.n_gpu_layers` | `0` = CPU, `-1` = alle Layer auf GPU |
| `hardware.n_threads` | CPU-Threads (`0` = auto) |
| `inference.*` | Default-Sampling-Parameter |

Umgebungsvariablen:

- `DEVDECK_GGUF_MODEL_PATH` — überschreibt `model.path`
- `DEVDECK_RUNTIME_CONFIG` — Pfad zu alternativer Config

## Nutzung

```python
from devdeck_runtime import ModelRunner

with ModelRunner() as runner:
    result = runner.complete("Hello!")
    print(result.text)

    for token in runner.complete_stream("Hello!", reset_cache=True):
        print(token, end="", flush=True)
```

CLI:

```powershell
python -m devdeck_runtime "Your prompt here"
python -m devdeck_runtime --stream "Your prompt here"
```

## KV-Cache

llama.cpp hält den KV-Cache pro `Llama`-Instanz. Standard: `reset_cache=True` bei jedem `complete()` / `complete_stream()` (frischer Prompt). Für Multi-Turn später: `reset_cache=False` und explizit `runner.reset_cache()`.

## Tests

Unit-Tests (ohne Modell):

```powershell
pytest tests/test_config.py -v
```

Smoke-Test (benötigt GGUF-Modell):

```powershell
$env:DEVDECK_GGUF_MODEL_PATH = "C:\path\to\model.gguf"
pytest tests/test_smoke.py -v -m smoke
```

## API

- `ModelRunner.load()` / `unload()` / `is_loaded`
- `ModelRunner.complete(prompt, ...)` → `CompletionResult`
- `ModelRunner.complete_stream(prompt, ...)` → `Iterator[str]`
- `ModelRunner.reset_cache()`
