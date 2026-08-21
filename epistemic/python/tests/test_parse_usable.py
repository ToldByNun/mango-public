from __future__ import annotations

from mango_epistemic.epistemic_engine import _fill_from_tool_outputs
from mango_epistemic.parse import usable_api_brief
from mango_epistemic.types import EpistemicResult


def test_usable_api_brief_rejects_import_failure_cards() -> None:
    assert usable_api_brief("discord: import failed: No module named 'discord'") is False
    assert usable_api_brief("commands: No module named 'commands'") is False
    assert usable_api_brief("foo: not found") is False
    assert usable_api_brief("Install failed for: discord.py") is False


def test_usable_api_brief_accepts_real_usage() -> None:
    brief = (
        "from collections import deque\n"
        "deque(iterable, maxlen=n) — maxlen auto-drops from the other end.\n"
        "append(x) / popleft() for a sliding window of timestamps."
    )
    assert usable_api_brief(brief) is True


def test_fill_from_tool_outputs_import_miss_overrides_hallucinated_exists() -> None:
    result = EpistemicResult(exists=True, details="I know discord Bot well", question="discord Bot")
    cards = [
        {
            "exists": False,
            "package": "discord",
            "error": "import failed: No module named 'discord'",
            "usage_card": "discord: import failed: No module named 'discord'",
        }
    ]
    _fill_from_tool_outputs(result, cards)
    assert result.exists is False
