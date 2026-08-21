from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from llama_cpp import Llama

from mango_runtime.config import load_config
from mango_runtime.cuda_env import ensure_cuda_on_path, has_cuda_backend, list_ggml_backends
from mango_runtime.gguf_loader import GGUFLoader
from mango_runtime.types import CompletionResult, InferenceConfig, RuntimeConfig

def neutralize_llama_destructor(llama: Any) -> None:
    """Stop llama-cpp-python from calling ExitStack.close() / CUDA free.

    `Llama.close()` runs `self._stack.close()`, which tears down the CUDA
    context. On Windows that often deadlocks the NVIDIA driver (especially
    with CUDA graphs or an in-flight decode) and freezes the whole desktop.
    Process exit is what actually reclaims VRAM.
    """
    if llama is None:
        return
    try:
        llama._closed = True
    except Exception:
        pass
    try:
        llama.close = lambda *args, **kwargs: None
    except Exception:
        pass


def close_llama_with_timeout(llama: Any, *, timeout_s: float = 4.0) -> bool:
    """Run the real Llama.close() off-thread. Return False if it hangs."""
    if llama is None:
        return True
    done = threading.Event()

    def _close() -> None:
        try:
            closer = getattr(type(llama), "close", None)
            if callable(closer):
                closer(llama)
            else:
                llama.close()
        except Exception:
            pass
        finally:
            done.set()

    worker = threading.Thread(target=_close, name="llama-close", daemon=True)
    worker.start()
    if done.wait(max(0.2, float(timeout_s))):
        return True
    neutralize_llama_destructor(llama)
    return False


def _disable_cuda_graphs() -> None:
    os.environ.setdefault("GGML_CUDA_ENABLE_GRAPHS", "0")
    os.environ.setdefault("GGML_CUDA_DISABLE_GRAPHS", "1")


DEFAULT_THOUGHT_MAX_TOKENS = 512
MAX_CONSTRAINED_TOOL_TOKENS = 384
_GEMMA4_STOPS = ("<turn|>", "<|turn>user", "<|turn>system", "<eos>")


def split_completion_budget(
    max_tokens: int,
    thought_max_tokens: int | None = None,
    tool_max_tokens: int | None = None,
) -> tuple[int, int]:
    """Split a completion budget into unconstrained thought vs constrained tail."""
    total = max(8, int(max_tokens))
    thought_cap = DEFAULT_THOUGHT_MAX_TOKENS if thought_max_tokens is None else int(thought_max_tokens)
    thought_cap = max(8, thought_cap)
    tool_cap = MAX_CONSTRAINED_TOOL_TOKENS if tool_max_tokens is None else max(32, int(tool_max_tokens))
    tool_floor = min(64, max(32, total // 2))
    thought = min(thought_cap, max(8, total - tool_floor))
    tool = max(32, total - thought)
    tool = min(tool, tool_cap)
    return thought, tool


def stitch_triggered_completion(thought: str, trigger: str, tail: str) -> str:
    """Join free-text thought with a grammar-constrained tool-call tail."""
    if not tail:
        return thought
    if trigger and thought.endswith(trigger):
        return thought + tail
    if not thought:
        return f"{trigger}{tail}"
    sep = "" if thought.endswith(("\n", " ")) else "\n"
    return f"{thought}{sep}{trigger}{tail}"


def is_gemma4_model(model_path: str | Path) -> bool:
    return "gemma" in Path(model_path).name.lower()


def format_completion_prompt(prompt: str, *, model_path: str | Path = "") -> str:
    """Apply the Gemma 4 chat prefix so generation is not stuck in the thought channel.

    The GGUF template, when thinking is off, closes `<|channel>thought` with
    `<channel|>` and then the model must emit the actual reply (a tool call).
    Raw prompts skip that suffix, so Gemma 4 coding sits in native thought
    and appears hung.
    """
    text = prompt or ""
    if "<|turn>" in text:
        return text
    if not is_gemma4_model(model_path):
        return text
    return (
        f"<|turn>user\n{text.rstrip()}\n"
        f"<turn|>\n<|turn>model\n<|channel>thought\n<channel|>"
    )


class ModelRunner:
    """
    Minimal GGUF runner backed by llama.cpp (llama-cpp-python).

    KV cache: llama.cpp prefix-matches the prompt when reset_cache=False.
    A full wipe is llama.reset() / reset_cache=True. Grammar is applied
    only after grammar_trigger (lazy constrained decoding) so CUDA graphs
    stay available during free-text thought.
    """

    def __init__(self, config: RuntimeConfig | str | None = None) -> None:
        if config is None or isinstance(config, str):
            self._config = load_config(config)
        else:
            self._config = config
        self._loader = GGUFLoader(self._config)
        self._llama: Llama | None = None
        self._grammar_cache: dict[str, Any] = {}

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    @property
    def is_loaded(self) -> bool:
        return self._llama is not None

    def load(self) -> None:
        if self._llama is not None:
            return
        ensure_cuda_on_path()
        backends = list_ggml_backends()
        n_gpu_layers = self._config.hardware.n_gpu_layers
        if n_gpu_layers != 0 and not has_cuda_backend():
            raise RuntimeError(
                "n_gpu_layers is set for GPU offload, but llama-cpp-python has no CUDA backend. "
                "Reinstall with CUDA: set CMAKE_ARGS='-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=120' "
                "and FORCE_CMAKE=1, then pip install --force-reinstall --no-cache-dir llama-cpp-python. "
                f"Registered backends: {backends or ['(none)']}"
            )
        kwargs = self._loader.llama_kwargs()
        n_threads = kwargs.pop("n_threads", None)
        if n_threads is not None:
            kwargs["n_threads"] = n_threads
        _disable_cuda_graphs()
        # Reduce CUDA allocator fragmentation
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
        os.environ.setdefault("GGML_CUDA_ENABLE_UNIFIED_MEMORY", "0")
        print(
            f"[mango] loading {self._loader.model_path.name} "
            f"(n_ctx={kwargs.get('n_ctx')} n_batch={kwargs.get('n_batch')} "
            f"n_ubatch={kwargs.get('n_ubatch')} flash_attn={kwargs.get('flash_attn')}) ...",
            file=sys.stderr,
            flush=True,
        )
        self._llama = Llama(**kwargs)
        print("[mango] model ready", file=sys.stderr, flush=True)

    def unload(self, *, timeout_s: float = 4.0) -> bool:
        """Free weights. Tries a real CUDA close, then abandons if it hangs."""
        llama = self._llama
        self._llama = None
        self._grammar_cache.clear()
        if llama is None:
            return True
        print("[mango] unloading model ...", file=sys.stderr, flush=True)
        ok = close_llama_with_timeout(llama, timeout_s=timeout_s)
        print(
            "[mango] model unloaded" if ok else "[mango] unload timed out; skipping CUDA free",
            file=sys.stderr,
            flush=True,
        )
        return ok

    def close(self) -> None:
        self.unload()

    def reset_cache(self) -> None:
        """Clear KV cache while keeping the loaded model weights."""
        if self._llama is not None:
            self._llama.reset()

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        stop: list[str] | None = None,
        reset_cache: bool = True,
        grammar: Any | None = None,
        grammar_trigger: str | None = None,
        thought_max_tokens: int | None = None,
        tool_max_tokens: int | None = None,
        force_grammar: bool = False,
        on_token: Callable[[str], None] | None = None,
        on_phase: Callable[[str], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> CompletionResult:
        llama = self._ensure_loaded()
        if reset_cache:
            llama.reset()
        prompt = format_completion_prompt(prompt, model_path=self._loader.model_path)
        print(
            f"[mango] generate prompt_chars={len(prompt)} force_grammar={force_grammar}",
            file=sys.stderr,
            flush=True,
        )
        started = time.monotonic()
        try:
            if grammar is not None and grammar_trigger:
                result = self._complete_lazy(
                    llama,
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    stop=stop,
                    grammar=grammar,
                    grammar_trigger=grammar_trigger,
                    thought_max_tokens=thought_max_tokens,
                    tool_max_tokens=tool_max_tokens,
                    force_grammar=force_grammar,
                    on_token=on_token,
                    on_phase=on_phase,
                    should_cancel=should_cancel,
                )
            else:
                inference = self._merge_inference(
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    stop=stop,
                )
                compiled = self._compile_grammar(grammar)
                if compiled is not None:
                    inference["grammar"] = compiled
                if on_token is None and should_cancel is None:
                    response = llama.create_completion(prompt=prompt, stream=False, **inference)
                    result = self._result_from_response(response)
                else:
                    text, choice, usage = self._stream_completion(
                        llama, prompt, inference, on_token, should_cancel=should_cancel
                    )
                    result = self._result_from_parts(text, choice, usage)
        finally:
            print(
                f"[mango] generate done {time.monotonic() - started:.1f}s "
                f"prompt_chars={len(prompt)} force_grammar={force_grammar}",
                file=sys.stderr,
                flush=True,
            )
        return result

    def complete_stream(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        stop: list[str] | None = None,
        reset_cache: bool = True,
        grammar: Any | None = None,
    ) -> Iterator[str]:
        llama = self._ensure_loaded()
        if reset_cache:
            llama.reset()
        prompt = format_completion_prompt(prompt, model_path=self._loader.model_path)

        inference = self._merge_inference(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
        )
        compiled = self._compile_grammar(grammar)
        if compiled is not None:
            inference["grammar"] = compiled

        stream = llama.create_completion(prompt=prompt, stream=True, **inference)
        for chunk in stream:
            delta = chunk["choices"][0].get("text", "")
            if delta:
                yield delta

    def __enter__(self) -> ModelRunner:
        self.load()
        return self

    def __exit__(self, *_: Any) -> None:
        self.unload()

    def _ensure_loaded(self) -> Llama:
        if self._llama is None:
            self.load()
        assert self._llama is not None
        return self._llama

    def _complete_lazy(
        self,
        llama: Llama,
        prompt: str,
        *,
        max_tokens: int | None,
        temperature: float | None,
        top_p: float | None,
        stop: list[str] | None,
        grammar: Any,
        grammar_trigger: str,
        thought_max_tokens: int | None,
        force_grammar: bool,
        tool_max_tokens: int | None = None,
        on_token: Callable[[str], None] | None = None,
        on_phase: Callable[[str], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> CompletionResult:
        defaults = self._config.inference
        total = max_tokens if max_tokens is not None else defaults.max_tokens
        thought_n, tool_n = split_completion_budget(total, thought_max_tokens, tool_max_tokens)
        stops = list(stop if stop is not None else defaults.stop)
        thought_stops = list(dict.fromkeys([*stops, grammar_trigger]))

        thought_params = self._merge_inference(
            max_tokens=thought_n,
            temperature=temperature,
            top_p=top_p,
            stop=thought_stops,
        )
        thought_seen = 0

        def _thought_token(delta: str) -> None:
            nonlocal thought_seen
            thought_seen += 1
            if thought_seen == 1 or thought_seen % 32 == 0:
                print(f"[mango] thought tokens={thought_seen}", file=sys.stderr, flush=True)
            if on_token is not None:
                on_token(delta)

        thought_text, thought_choice, thought_usage = self._stream_completion(
            llama, prompt, thought_params, _thought_token, should_cancel=should_cancel
        )
        if should_cancel is not None and should_cancel():
            prompt_tokens = int(thought_usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(thought_usage.get("completion_tokens", 0) or 0)
            if completion_tokens <= 0:
                completion_tokens = self._estimate_tokens(llama, thought_text)
            return CompletionResult(
                text=thought_text,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                stopped_eos=True,
                model_path=str(self._loader.model_path),
            )
        preview = thought_text.replace("\n", " ").strip()
        if len(preview) > 240:
            preview = preview[:239] + "…"
        print(
            f"[mango] thought_chars={len(thought_text)} {preview!r}",
            file=sys.stderr,
            flush=True,
        )
        completion_tokens = int(thought_usage.get("completion_tokens", 0) or 0)
        if completion_tokens <= 0:
            completion_tokens = self._estimate_tokens(llama, thought_text)
        fired = self._generated_contains_trigger(llama, grammar_trigger, completion_tokens)

        if not fired and not force_grammar:
            prompt_tokens = int(thought_usage.get("prompt_tokens", 0) or 0)
            return CompletionResult(
                text=thought_text,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                stopped_eos=thought_choice.get("finish_reason") == "stop",
                model_path=str(self._loader.model_path),
            )

        continuation = prompt + thought_text
        if not continuation.endswith(grammar_trigger):
            continuation += grammar_trigger

        tool_params = self._merge_inference(
            max_tokens=tool_n,
            temperature=temperature,
            top_p=top_p,
            stop=stops,
        )
        compiled = self._compile_grammar(grammar)
        if compiled is not None:
            tool_params["grammar"] = compiled
        if on_phase is not None:
            on_phase("tool_grammar")
        print(
            f"[mango] constrained tool decode (max_tokens={tool_n}) ...",
            file=sys.stderr,
            flush=True,
        )
        tool_seen = 0

        def _tool_complete(partial: str) -> bool:
            """Stop as soon as a full tool call parses (incl. write_file fence)."""
            try:
                from mango_tools.tool_parser import parse_tool_calls
            except ImportError:
                return False
            stitched = stitch_triggered_completion(thought_text, grammar_trigger, partial)
            return bool(parse_tool_calls(stitched))

        def _tool_heartbeat(delta: str) -> None:
            nonlocal tool_seen
            tool_seen += 1
            if tool_seen == 1 or tool_seen % 64 == 0:
                print(f"[mango] tool tokens={tool_seen}", file=sys.stderr, flush=True)
            # Tool JSON is not shown as thought stream in the UI.
            del delta

        tool_text, tool_choice, tool_usage = self._stream_completion(
            llama,
            continuation,
            tool_params,
            _tool_heartbeat,
            should_cancel=should_cancel,
            should_stop=_tool_complete,
        )
        tool_preview = tool_text.replace("\n", " ").strip()
        if len(tool_preview) > 500:
            tool_preview = tool_preview[:499] + "…"
        print(f"[mango] tool_json={tool_preview!r}", file=sys.stderr, flush=True)
        stitched = stitch_triggered_completion(thought_text, grammar_trigger, tool_text)

        prompt_tokens = int(thought_usage.get("prompt_tokens", 0) or 0)
        tool_tokens = int(tool_usage.get("completion_tokens", 0) or 0)
        if tool_tokens <= 0:
            tool_tokens = self._estimate_tokens(llama, tool_text)
        completion_tokens = completion_tokens + tool_tokens
        return CompletionResult(
            text=stitched,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            stopped_eos=tool_choice.get("finish_reason") == "stop",
            model_path=str(self._loader.model_path),
        )

    def _stream_completion(
        self,
        llama: Llama,
        prompt: str,
        params: dict[str, Any],
        on_token: Callable[[str], None] | None,
        *,
        should_cancel: Callable[[], bool] | None = None,
        should_stop: Callable[[str], bool] | None = None,
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        print(
            f"[mango] waiting for first token (prompt eval) prompt_chars={len(prompt)} ...",
            file=sys.stderr,
            flush=True,
        )
        stream = llama.create_completion(prompt=prompt, stream=True, **params)
        text = ""
        last: dict[str, Any] = {}
        first = True
        try:
            for chunk in stream:
                if should_cancel is not None and should_cancel():
                    break
                last = chunk
                delta = chunk["choices"][0].get("text", "")
                if delta:
                    if first:
                        prefill_s = time.monotonic() - started
                        usage_hint = chunk.get("usage") or last.get("usage") or {}
                        prompt_tokens = (
                            usage_hint.get("prompt_tokens") if isinstance(usage_hint, dict) else None
                        )
                        token_note = f" prompt_tokens={prompt_tokens}" if prompt_tokens else ""
                        print(
                            f"[mango] prefill {prefill_s:.2f}s{token_note} prompt_chars={len(prompt)}",
                            file=sys.stderr,
                            flush=True,
                        )
                        first = False
                    text += delta
                    if on_token is not None:
                        on_token(delta)
                    if should_stop is not None and should_stop(text):
                        break
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        choice = last.get("choices", [{}])[0] if last else {}
        usage = last.get("usage", {}) if last else {}
        if not isinstance(usage, dict):
            usage = {}
        if not usage.get("completion_tokens"):
            usage = {
                **usage,
                "completion_tokens": self._estimate_tokens(llama, text),
            }
        return text, choice, usage

    def _estimate_tokens(self, llama: Llama, text: str) -> int:
        if not text:
            return 0
        try:
            encoded = text.encode("utf-8")
            tokens = llama.tokenize(encoded, add_bos=False)
            return max(1, len(tokens))
        except Exception:
            return max(1, (len(text) + 3) // 4)

    def _result_from_parts(
        self,
        text: str,
        choice: dict[str, Any],
        usage: dict[str, Any],
    ) -> CompletionResult:
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        return CompletionResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=int(usage.get("total_tokens", 0) or prompt_tokens + completion_tokens),
            stopped_eos=choice.get("finish_reason") == "stop",
            model_path=str(self._loader.model_path),
        )

    def _generated_contains_trigger(
        self,
        llama: Llama,
        trigger: str,
        completion_tokens: int,
    ) -> bool:
        if completion_tokens <= 0:
            return False
        try:
            ids = list(llama._input_ids)
            gen = ids[-completion_tokens:]
            blob = llama.detokenize(gen)
            text = blob.decode("utf-8", "replace") if isinstance(blob, (bytes, bytearray)) else str(blob)
        except Exception:
            return False
        return trigger in text

    def _compile_grammar(self, grammar: Any) -> Any:
        if grammar is None:
            return None
        if not isinstance(grammar, str):
            return grammar
        cached = self._grammar_cache.get(grammar)
        if cached is not None:
            return cached
        try:
            from llama_cpp import LlamaGrammar
        except ImportError:  # pragma: no cover - older llama-cpp-python layouts
            from llama_cpp.llama_grammar import LlamaGrammar

        print("[mango] compiling tool grammar ...", file=sys.stderr, flush=True)
        compiled = LlamaGrammar.from_string(grammar)
        print("[mango] tool grammar ready", file=sys.stderr, flush=True)
        self._grammar_cache[grammar] = compiled
        return compiled

    def _merge_inference(
        self,
        *,
        max_tokens: int | None,
        temperature: float | None,
        top_p: float | None,
        stop: list[str] | None,
    ) -> dict[str, Any]:
        defaults = self._config.inference
        stops = list(stop if stop is not None else defaults.stop)
        if is_gemma4_model(self._loader.model_path):
            for marker in _GEMMA4_STOPS:
                if marker not in stops:
                    stops.append(marker)
        merged = InferenceConfig(
            max_tokens=max_tokens if max_tokens is not None else defaults.max_tokens,
            temperature=temperature if temperature is not None else defaults.temperature,
            top_p=top_p if top_p is not None else defaults.top_p,
            stop=stops,
        )
        params: dict[str, Any] = {
            "max_tokens": merged.max_tokens,
            "temperature": merged.temperature,
            "top_p": merged.top_p,
            "top_k": 40,
            "min_p": 0.05,
            "repeat_penalty": 1.0,
        }
        if merged.stop:
            params["stop"] = merged.stop
        return params

    def _result_from_response(self, response: dict[str, Any]) -> CompletionResult:
        choice = response["choices"][0]
        usage = response.get("usage", {})
        return CompletionResult(
            text=str(choice.get("text", "")),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
            stopped_eos=choice.get("finish_reason") == "stop",
            model_path=str(self._loader.model_path),
        )
