from __future__ import annotations

import re
from typing import Any

from mango_cot.parse import parse_reasoning_payload
from mango_epistemic.types import EpistemicResult, Evidence

_JUNK_SIG = re.compile(r"\(/,\s*\*args,\s*\*\*kwargs\)|\(\s*\*args,\s*\*\*kwargs\s*\)")


def parse_epistemic_result(question: str, payload: Any, *, extra_evidence: list[Evidence] | None = None) -> EpistemicResult:
    data: dict[str, Any] = {}
    if isinstance(payload, dict):
        data = payload
    elif isinstance(payload, str):
        data = parse_reasoning_payload(payload)
        if not _has_structured_fields(data):
            brief = payload.strip()
            if brief:
                data = {"exists": True, "details": brief}

    exists = data.get("exists")
    if exists is not None and not isinstance(exists, bool):
        exists = str(exists).strip().lower() in {"true", "yes", "1"}

    evidence = _parse_evidence(data.get("evidence"))
    if not evidence and extra_evidence:
        evidence = list(extra_evidence)

    conflicts = data.get("conflicts")
    if conflicts == [] or conflicts is None:
        conflicts_list = None
    elif isinstance(conflicts, list):
        conflicts_list = [str(item) for item in conflicts if str(item).strip()]
    elif isinstance(conflicts, str) and conflicts.strip():
        conflicts_list = [conflicts.strip()]
    else:
        conflicts_list = None

    signature = _text(data.get("signature") or data.get("details_signature"))
    details = _text(data.get("details") or data.get("usage_card"))
    version = _text(data.get("version"))
    if signature and not usable_api_signature(signature):
        signature = ""

    if not evidence and extra_evidence:
        evidence = list(extra_evidence)

    return EpistemicResult(
        exists=exists,
        signature=signature or None,
        details=details or None,
        version=version or None,
        evidence=_dedupe_evidence(evidence)[:5],
        conflicts=conflicts_list,
        question=question,
    )


def usable_api_signature(value: Any) -> bool:
    text = str(value or "").strip()
    if "(" not in text:
        return False
    if _JUNK_SIG.search(text) and text.count("(") <= 1:
        return False
    return True


def usable_api_brief(value: Any) -> bool:
    text = str(value or "").strip()
    if len(text) < 40:
        return False
    low = text.lower()
    if any(token in low for token in ("i will ", "i'll ", "let me ", "using the doc_lookup", "using the tool")):
        return False
    if _JUNK_SIG.search(text) and "append" not in low and "import " not in low:
        return False
    return True


def _has_structured_fields(data: dict[str, Any]) -> bool:
    return bool(data.get("signature") or data.get("details") or data.get("exists") is not None)


def evidence_from_tool_outputs(outputs: list[Any]) -> list[Evidence]:
    items: list[Evidence] = []
    for output in outputs:
        if not isinstance(output, dict):
            continue
        if output.get("results"):
            for row in output["results"][:5]:
                if not isinstance(row, dict):
                    continue
                items.append(
                    Evidence(
                        source=str(row.get("url") or row.get("source") or "web_research"),
                        snippet=_clip_snippet(str(row.get("snippet") or row.get("title") or "")),
                    )
                )
        elif output.get("url"):
            items.append(
                Evidence(
                    source=str(output.get("url")),
                    snippet=str(output.get("hint") or output.get("status") or ""),
                )
            )
        elif output.get("signature") or output.get("doc"):
            snippet = str(output.get("signature") or output.get("doc") or "")
            items.append(
                Evidence(
                    source=str(output.get("qualname") or output.get("library") or output.get("package") or "inspect"),
                    snippet=_clip_snippet(snippet),
                )
            )
        elif output.get("error") and output.get("exists") is False:
            items.append(
                Evidence(
                    source=str(output.get("library") or output.get("package") or "inspect"),
                    snippet=_clip_snippet(str(output.get("error"))),
                )
            )
        elif output.get("hint"):
            items.append(
                Evidence(
                    source=str(output.get("library") or output.get("package") or "lookup"),
                    snippet=str(output["hint"]),
                )
            )
    return _dedupe_evidence(items)


def _parse_evidence(raw: Any) -> list[Evidence]:
    if not raw:
        return []
    items: list[Evidence] = []
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict):
                items.append(
                    Evidence(
                        source=str(row.get("source") or row.get("url") or "unknown"),
                        snippet=str(row.get("snippet") or row.get("title") or ""),
                    )
                )
            else:
                items.append(Evidence(source="unknown", snippet=str(row)))
    elif isinstance(raw, str):
        items.append(Evidence(source="model", snippet=raw))
    return items


def _dedupe_evidence(items: list[Evidence]) -> list[Evidence]:
    seen: set[str] = set()
    unique: list[Evidence] = []
    for item in items:
        key = item.source + "|" + item.snippet[:80]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clip_snippet(text: str, limit: int = 160) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[-limit:]
