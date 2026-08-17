from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from llama_cpp import Llama

from devdeck_runtime.config import load_config
from devdeck_runtime.gguf_loader import GGUFLoader
from devdeck_runtime.types import CompletionResult, InferenceConfig, RuntimeConfig


class ModelRunner:
    """
    Minimal GGUF runner backed by llama.cpp (llama-cpp-python).

    KV cache: llama.cpp keeps prompt KV state on the Llama instance.
    Call reset_cache() before a fresh unrelated prompt, or set
    reset_cache=True on complete() / complete_stream() (default).
    """

    def __init__(self, config: RuntimeConfig | str | None = None) -> None:
        if config is None or isinstance(config, str):
            self._config = load_config(config)
        else:
            self._config = config
        self._loader = GGUFLoader(self._config)
        self._llama: Llama | None = None

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    @property
    def is_loaded(self) -> bool:
        return self._llama is not None

    def load(self) -> None:
        if self._llama is not None:
            return
        kwargs = self._loader.llama_kwargs()
        n_threads = kwargs.pop("n_threads", None)
        if n_threads is not None:
            kwargs["n_threads"] = n_threads
        self._llama = Llama(**kwargs)

    def unload(self) -> None:
        if self._llama is None:
            return
        self._llama.close()
        self._llama = None

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
    ) -> CompletionResult:
        llama = self._ensure_loaded()
        if reset_cache:
            llama.reset()

        inference = self._merge_inference(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
        )
        response = llama.create_completion(prompt=prompt, stream=False, **inference)
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

    def complete_stream(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        stop: list[str] | None = None,
        reset_cache: bool = True,
    ) -> Iterator[str]:
        llama = self._ensure_loaded()
        if reset_cache:
            llama.reset()

        inference = self._merge_inference(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
        )

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

    def _merge_inference(
        self,
        *,
        max_tokens: int | None,
        temperature: float | None,
        top_p: float | None,
        stop: list[str] | None,
    ) -> dict[str, Any]:
        defaults = self._config.inference
        merged = InferenceConfig(
            max_tokens=max_tokens if max_tokens is not None else defaults.max_tokens,
            temperature=temperature if temperature is not None else defaults.temperature,
            top_p=top_p if top_p is not None else defaults.top_p,
            stop=stop if stop is not None else defaults.stop,
        )
        params: dict[str, Any] = {
            "max_tokens": merged.max_tokens,
            "temperature": merged.temperature,
            "top_p": merged.top_p,
        }
        if merged.stop:
            params["stop"] = merged.stop
        return params
