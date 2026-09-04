"""fetch_url — read a web page / API docs when packages aren't installed locally."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from mango_epistemic.research_tools import USER_AGENT, web_research


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self._parts.append(text)


def fetch_url(url: str, *, max_chars: int = 6000, _context: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET a URL and return readable text (for online API docs)."""
    target = str(url or "").strip()
    if not target.startswith(("http://", "https://")):
        return {"ok": False, "error": "url_must_be_http", "url": target}
    request = Request(target, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=12) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="replace")
            final_url = str(response.geturl())
    except (URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": str(exc), "url": target}

    ctype = "html" if re.search(r"<html|<!doctype", raw[:500], re.I) else "text"
    if ctype == "html":
        parser = _TextExtractor()
        try:
            parser.feed(raw)
            text = "\n".join(parser._parts)
        except Exception:
            text = re.sub(r"<[^>]+>", " ", raw)
            text = " ".join(text.split())
    else:
        text = raw
    text = text.strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return {"ok": True, "url": final_url, "chars": len(text), "text": text}


def register_web_tools(registry: Any) -> None:
    if not registry.has("web_research"):
        registry.register(
            "web_research",
            web_research,
            description="Search the web for API docs / examples when local packages are missing.",
            parameters={
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Max results", "default": 5},
            },
            required=["query"],
        )
    if not registry.has("fetch_url"):
        registry.register(
            "fetch_url",
            fetch_url,
            description="Fetch and extract text from an http(s) URL (API docs pages).",
            parameters={
                "url": {"type": "string", "description": "https://... docs URL"},
                "max_chars": {"type": "integer", "description": "Cap returned text", "default": 6000},
            },
            required=["url"],
        )
