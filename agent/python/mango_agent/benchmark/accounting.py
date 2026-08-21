"""Count every model complete() call, including CoT and epistemic sub-agent turns."""

from __future__ import annotations

from typing import Any


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


class AccountingModelRunner:
    """Wrap a model runner and sum prompt/completion tokens across the whole loop."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.complete_calls = 0
        self.estimated = False

    def complete(self, prompt: str, **kwargs: Any) -> Any:
        result = self.inner.complete(prompt, **kwargs)
        prompt_tokens = int(getattr(result, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(result, "completion_tokens", 0) or 0)
        if prompt_tokens <= 0:
            prompt_tokens = _estimate_tokens(prompt)
            self.estimated = True
        text = str(getattr(result, "text", result) or "")
        if completion_tokens <= 0:
            completion_tokens = _estimate_tokens(text)
            self.estimated = True
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.complete_calls += 1
        return result

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def close(self) -> None:
        unload = getattr(self.inner, "unload", None)
        if callable(unload):
            unload()
        close = getattr(self.inner, "close", None)
        if callable(close):
            close()
