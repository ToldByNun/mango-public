from __future__ import annotations

import re

from mango_agent.prompt import feedback

_LOCK_CTOR = re.compile(r"\b(?:threading\.)?(?:Lock|RLock)\s*\(")
_PER_CLIENT_LOCK = re.compile(
    r"defaultdict\s*\(\s*(?:threading\.)?(?:Lock|RLock)\b"
    r"|self\.(?:client_)?locks\b"
    r"|\blocks\s*\[\s*client"
    r"|Lock\s*\(\s*\)\s*\)",
    re.IGNORECASE,
)
_CLIENT_KEY = re.compile(r"\bclient_id\b|\bclients\s*\[")


def has_per_client_locks(source: str) -> bool:
    text = source or ""
    if _PER_CLIENT_LOCK.search(text):
        return True
    if _CLIENT_KEY.search(text) and text.count("Lock(") + text.count("RLock(") >= 2:
        return True
    return bool(re.search(r"locks\s*\[", text) and _LOCK_CTOR.search(text))


def has_single_global_lock(source: str) -> bool:
    text = source or ""
    count = len(_LOCK_CTOR.findall(text))
    if count != 1:
        return False
    return not has_per_client_locks(text)


def lock_coarsened(before: str, after: str) -> bool:
    """True when fine-grained/per-client locks were collapsed to one global lock."""
    if not (before or "").strip() or not (after or "").strip():
        return False
    if not has_per_client_locks(before):
        return False
    if has_per_client_locks(after):
        return False
    return has_single_global_lock(after) or bool(_LOCK_CTOR.search(after))


def review_message(*, coarsened: bool) -> str:
    return feedback("coarsened") if coarsened else feedback()


def coarsen_after_read_message() -> str:
    return feedback()
