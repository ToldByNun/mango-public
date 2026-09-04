from pathlib import Path

from mango_tools.knowledge import open_vault_note, rag_search, read_brief, refresh_index


def test_brief():
    out = read_brief()
    assert out["ok"] is True
    assert "Mango" in out["brief"]


def test_vault_open_and_links():
    out = open_vault_note("Architecture")
    assert out["ok"] is True
    assert "Agent Loop" in " ".join(out.get("links") or []) or "agent-loop" in (out.get("links") or [])


def test_rag_search_roundtrip(tmp_path: Path, monkeypatch):
    # Use real repo knowledge; force refresh into default .mango path is fine
    rebuilt = refresh_index()
    assert rebuilt["ok"] is True
    assert rebuilt["chunks"] >= 3
    hits = rag_search("roblox studio plugin host", refresh=False)
    assert hits["ok"] is True
    assert hits["hits"]
