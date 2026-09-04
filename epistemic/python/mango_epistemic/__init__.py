"""Mango Epistemic — isolated sub-agents that share one ModelRunner."""

from mango_epistemic.codebase_research import register_research_codebase, run_codebase_research
from mango_epistemic.epistemic_engine import EpistemicEngine, ask_epistemic, register_ask_epistemic
from mango_epistemic.types import EpistemicResult, EpistemicResultDict, Evidence, InstallHintDict

__all__ = [
    "EpistemicEngine",
    "EpistemicResult",
    "EpistemicResultDict",
    "Evidence",
    "InstallHintDict",
    "ask_epistemic",
    "register_ask_epistemic",
    "register_research_codebase",
    "run_codebase_research",
]
