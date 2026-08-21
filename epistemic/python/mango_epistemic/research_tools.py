from __future__ import annotations

import importlib
import inspect
import re
from html.parser import HTMLParser
from typing import Any
from urllib.error import URLError
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

USER_AGENT = "Mango/0.1 (local epistemic research)"
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capture = False
        self._href = ""
        self.results: list[dict[str, str]] = []
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        data = dict(attrs)
        href = data.get("href") or ""
        css = data.get("class") or ""
        if "result__a" in css or href.startswith("http"):
            self._capture = True
            self._href = href
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._capture:
            return
        title = " ".join("".join(self._buf).split())
        self._capture = False
        if title and self._href:
            self.results.append({"title": title, "url": self._href})


def web_research(
    query: str,
    *,
    max_results: int = 5,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search the web. Uses an injected backend when present (tests / offline)."""
    context = _context or {}
    backend = context.get("web_research_backend")
    if callable(backend):
        return _normalize_search(backend(query), query, max_results)
    return duckduckgo_search(query, max_results=max_results)


def duckduckgo_search(query: str, *, max_results: int = 5, timeout: int = 8) -> dict[str, Any]:
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 — user-controlled research query
            html = response.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "query": query,
            "results": [],
            "error": f"web_research failed: {exc}",
        }

    parser = _LinkParser()
    parser.feed(html)
    results = []
    seen: set[str] = set()
    for item in parser.results:
        href = item["url"]
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = urljoin("https://duckduckgo.com", href)
        if href in seen or "duckduckgo.com" in href:
            continue
        seen.add(href)
        results.append({"title": item["title"], "url": href, "snippet": item["title"]})
        if len(results) >= max_results:
            break
    return {"query": query, "results": results, "error": None}


def doc_lookup(
    library: str,
    symbol: str = "",
    *,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect a library/symbol and return its live signature and docstring."""
    return inspect_symbol(library, symbol)


def package_source_lookup(
    package: str,
    symbol: str = "",
    *,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect an importable package/symbol and return its live signature and docstring."""
    return inspect_symbol(package, symbol)


def inspect_symbol(package: str, symbol: str = "") -> dict[str, Any]:
    """Resolve `package.symbol` and return a source card the API sub-agent can read."""
    try:
        obj, qualname = _resolve_symbol(package, symbol)
    except ImportError as exc:
        return {
            "status": "missing",
            "exists": False,
            "library": package,
            "package": package,
            "symbol": symbol or None,
            "error": f"import failed: {exc}",
        }
    except AttributeError as exc:
        return {
            "status": "missing",
            "exists": False,
            "library": package,
            "package": package,
            "symbol": symbol or None,
            "error": f"attribute failed: {exc}",
        }
    except ValueError as exc:
        return {
            "status": "invalid",
            "exists": False,
            "library": package,
            "package": package,
            "symbol": symbol or None,
            "error": str(exc),
        }

    doc = inspect.getdoc(obj) or ""
    blurb = doc.split("\n\n", 1)[0].strip()[:700]
    member_limit = 4 if inspect.ismodule(obj) else 8
    members = _public_members(obj, qualname, limit=member_limit)
    source = None if inspect.ismodule(obj) else _source_excerpt(obj, limit=800)
    source_file = _source_file(obj)
    signature = _format_signature(obj, qualname)
    if members and (not signature or _junk_signature(signature) or "(" not in signature):
        signature = " | ".join(f"{qualname}.{item['name']}()" for item in members[:6])
    if members:
        details = ", ".join(item["name"] for item in members[:6])
    else:
        details = blurb or signature
    payload = {
        "status": "ok",
        "exists": True,
        "library": package,
        "package": package,
        "symbol": symbol or None,
        "qualname": qualname,
        "signature": signature,
        "doc": doc[:1_800] if doc else None,
        "details": details,
        "kind": _kind(obj),
        "members": members or None,
    }
    if source_file:
        payload["source_file"] = source_file
    if source:
        payload["source"] = source
    payload["usage_card"] = format_usage_card(payload)
    return payload


_USAGE_HINTS: dict[tuple[str, str], dict[str, str]] = {
    ("collections", "deque"): {
        "use": "sliding window / queue (timestamps, recent items)",
        "import": "from collections import deque",
        "example": "w = deque()\nw.append(now)\nwhile w and now - w[0] > window:\n    w.popleft()  # O(1)",
        "notes": "append/popleft are O(1); list.pop(0) is O(n). deque(maxlen=n) auto-drops from the other end.",
    },
    ("threading", "lock"): {
        "use": "mutual exclusion for one piece of shared state",
        "import": "from threading import Lock",
        "example": "self._lock = Lock()  # factory, not a class to subclass\nwith self._lock:\n    ...",
        "notes": "One lock per shared structure. Independent clients need a Lock per client, not one global lock.",
    },
    ("time", "monotonic"): {
        "use": "elapsed time for windows; not wall clock",
        "import": "from time import monotonic",
        "example": "t0 = monotonic()\nelapsed = monotonic() - t0",
        "notes": "Do not mix monotonic() with time.time() in the same window. Not convertible to datetime.",
    },
    ("time", "time"): {
        "use": "wall-clock epoch seconds",
        "import": "from time import time",
        "example": "now = time()",
        "notes": "Can jump (NTP). Prefer monotonic() for durations.",
    },
    ("json", "dumps"): {
        "use": "serialize a Python object to a JSON string",
        "import": "import json",
        "example": "text = json.dumps(obj, indent=2)",
        "notes": "Default cannot encode datetime/set. Default ensure_ascii=True.",
    },
    ("argparse", "argumentparser"): {
        "use": "CLI flags",
        "import": "import argparse",
        "example": "p = argparse.ArgumentParser()\np.add_argument('--path')\nargs = p.parse_args()",
        "notes": "add_argument name is '--flag' or positional. parse_args() reads sys.argv.",
    },
    ("pathlib", "path"): {
        "use": "filesystem paths",
        "import": "from pathlib import Path",
        "example": "p = Path('data.csv')\ntext = p.read_text(encoding='utf-8')",
        "notes": "Path is the object; do not use os.path unless matching existing code.",
    },
    ("pandas", "read_csv"): {
        "use": "load a CSV into a DataFrame",
        "import": "import pandas as pd",
        "example": "df = pd.read_csv(path)",
        "notes": "Keyword args only for engine/encoding options. File must exist at runtime (compile() will not catch that).",
    },
    ("concurrent.futures", "threadpoolexecutor"): {
        "use": "run callables in a pool of worker threads",
        "import": "from concurrent.futures import ThreadPoolExecutor",
        "example": "with ThreadPoolExecutor(max_workers=8) as pool:\n    futs = [pool.submit(fn, item) for item in items]\n    for fut in futs:\n        fut.result()",
        "notes": "max_workers=8+ for stress tests. Catch handler exceptions inside the worker; a raised result() fails only that future.",
    },
}


def has_usage_hint(package: str, symbol: str = "") -> bool:
    return (str(package or "").lower(), str(symbol or "").lower()) in _USAGE_HINTS


def format_usage_card(payload: dict[str, Any]) -> str:
    """Targeted brief: import, call, one snippet, pitfalls. Not a module dump."""
    if payload.get("exists") is False:
        name = payload.get("qualname") or payload.get("package") or "symbol"
        err = payload.get("error") or "not found"
        return f"{name}: {err}"
    package = str(payload.get("package") or payload.get("library") or "").strip()
    symbol = str(payload.get("symbol") or "").strip()
    hint = _USAGE_HINTS.get((package.lower(), symbol.lower()))
    lines: list[str] = []
    qual = str(payload.get("qualname") or package).strip()
    if qual:
        lines.append(qual)
    if hint:
        lines.append(f"for: {hint['use']}")
        lines.append(hint["import"])
    signature = str(payload.get("signature") or "").strip()
    if signature and not _junk_signature(signature) and " | " not in signature:
        lines.append(f"call: {signature}")
    kind = str(payload.get("kind") or "")
    if hint:
        lines.append("example:")
        lines.append(hint["example"])
        lines.append(f"notes: {hint['notes']}")
    else:
        doc = str(payload.get("doc") or "").strip()
        if doc and kind != "module":
            lines.append(doc.split("\n\n", 1)[0].strip()[:400])
        members = payload.get("members") or []
        if isinstance(members, list) and members:
            bits = []
            for row in members[:4]:
                if not isinstance(row, dict):
                    continue
                sig = str(row.get("signature") or row.get("name") or "").strip()
                if sig and " | " not in sig:
                    bits.append(sig)
            if bits:
                lines.append("methods: " + "; ".join(bits))
        if kind == "module":
            lines.append("Look up a concrete symbol (e.g. time.monotonic), not the whole module.")
    return "\n".join(part for part in lines if part).strip()


def _resolve_symbol(package: str, symbol: str = "") -> tuple[Any, str]:
    parts = [part for part in (package or "").split(".") if part]
    attr_parts = [part for part in (symbol or "").split(".") if part]
    if attr_parts and parts and attr_parts[: len(parts)] == parts:
        attr_parts = attr_parts[len(parts) :]
    if not parts:
        raise ValueError("library/package name is required")
    for part in parts + attr_parts:
        if not _NAME.match(part):
            raise ValueError(f"invalid identifier: {part}")

    module_parts = list(parts)
    module = None
    import_error: ImportError | None = None
    while module_parts:
        name = ".".join(module_parts)
        try:
            module = importlib.import_module(name)
            break
        except ImportError as exc:
            import_error = exc
            attr_parts = [module_parts.pop()] + attr_parts
    if module is None:
        raise import_error or ImportError(package)

    obj: Any = module
    for name in attr_parts:
        obj = getattr(obj, name)
    qual = ".".join([module.__name__, *attr_parts]) if attr_parts else module.__name__
    return obj, qual


_PREFERRED_METHODS = (
    "append",
    "appendleft",
    "pop",
    "popleft",
    "extend",
    "clear",
    "acquire",
    "release",
    "locked",
    "read",
    "write",
    "add_argument",
    "parse_args",
)


def _public_members(obj: Any, qualname: str, *, limit: int = 16) -> list[dict[str, str]]:
    names = _member_names(obj)
    members: list[dict[str, str]] = []
    for name in names:
        if len(members) >= limit:
            break
        if not _NAME.match(name) or name.startswith("_"):
            continue
        try:
            child = getattr(obj, name)
        except Exception:
            continue
        if inspect.ismodule(child):
            continue
        if not (callable(child) or inspect.isclass(child)):
            continue
        members.append(
            {
                "name": name,
                "signature": _format_signature(child, f"{qualname}.{name}"),
            }
        )
    return members


def _member_names(obj: Any) -> list[str]:
    preferred_mod = {
        "threading": ("Lock", "RLock", "Thread", "local"),
        "collections": ("deque", "defaultdict", "namedtuple", "Counter"),
        "time": ("monotonic", "time", "sleep"),
        "json": ("dumps", "loads", "load", "dump"),
        "argparse": ("ArgumentParser",),
        "pathlib": ("Path",),
        "concurrent.futures": ("ThreadPoolExecutor", "as_completed"),
    }
    if inspect.ismodule(obj):
        names = [str(item) for item in (getattr(obj, "__all__", None) or []) if str(item).strip()]
        if not names:
            names = [name for name in dir(obj) if not name.startswith("_")]
        first = [name for name in preferred_mod.get(str(getattr(obj, "__name__", "")), ()) if name in names]
        rest = [name for name in names if name not in first]
        return first + rest
    listed = [name for name in dir(obj) if _NAME.match(name) and not name.startswith("_")]
    preferred = [name for name in _PREFERRED_METHODS if name in listed]
    rest = [name for name in listed if name not in preferred]
    return preferred + rest


def _source_file(obj: Any) -> str | None:
    try:
        path = inspect.getsourcefile(obj) or inspect.getfile(obj)
    except (OSError, TypeError):
        return None
    if not path or path.startswith("<"):
        return None
    return path


def _source_excerpt(obj: Any, *, limit: int = 2_400) -> str | None:
    try:
        source = inspect.getsource(obj)
    except (OSError, TypeError):
        doc = inspect.getdoc(obj) or ""
        return doc.strip()[:limit] or None
    text = source.strip()
    if not text:
        return None
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _format_signature(obj: Any, qualname: str) -> str:
    header = _doc_call_header(obj, qualname)
    target = obj
    if inspect.isclass(obj):
        target = getattr(obj, "__init__", obj)
    try:
        sig = str(inspect.signature(target))
    except (TypeError, ValueError):
        return header or (f"{qualname}()" if callable(obj) or inspect.isclass(obj) else qualname)
    if inspect.isclass(obj) and sig.startswith("(self"):
        sig = "(" + sig[len("(self") :].lstrip(", ")
        if not sig.startswith("("):
            sig = "(" + sig
    rendered = f"{qualname}{sig}"
    if _junk_signature(rendered):
        return header or f"{qualname}()"
    return rendered


def _doc_call_header(obj: Any, qualname: str) -> str | None:
    doc = inspect.getdoc(obj) or getattr(obj, "__doc__", None) or ""
    first = str(doc).strip().splitlines()[0].strip() if str(doc).strip() else ""
    if "(" not in first:
        return None
    if first.lower().startswith(qualname.lower()):
        return first.split("-->", 1)[0].split("->", 1)[0].strip()
    short = first.split("-->", 1)[0].split("--", 1)[0].split("->", 1)[0].strip()
    if short.endswith(")") or "[" in short:
        if short[0].isalpha() or short.startswith(qualname.split(".")[-1]):
            return short
    return None


def _junk_signature(text: str) -> bool:
    blob = str(text or "")
    if "(" not in blob:
        return True
    compact = blob.replace(" ", "")
    return "(*args,**kwargs)" in compact or "(/,*args,**kwargs)" in compact


def _kind(obj: Any) -> str:
    if inspect.ismodule(obj):
        return "module"
    if inspect.isclass(obj):
        return "class"
    if inspect.isfunction(obj) or inspect.ismethod(obj) or inspect.isbuiltin(obj):
        return "function"
    return type(obj).__name__


def _normalize_search(payload: Any, query: str, max_results: int) -> dict[str, Any]:
    if isinstance(payload, dict) and "results" in payload:
        results = list(payload.get("results") or [])[:max_results]
        return {"query": query, "results": results, "error": payload.get("error")}
    if isinstance(payload, list):
        return {"query": query, "results": payload[:max_results], "error": None}
    return {"query": query, "results": [{"title": str(payload), "url": "", "snippet": str(payload)}], "error": None}
