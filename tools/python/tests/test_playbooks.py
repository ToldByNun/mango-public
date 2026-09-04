from mango_tools.playbooks import load_playbooks, lookup_playbook


def test_loads_repo_playbooks():
    books = load_playbooks()
    names = {b["name"] for b in books}
    assert "playwright-site-login" in names
    assert "mango-studio-host" in names


def test_lookup_playwright():
    out = lookup_playbook("playwright login browser auth")
    assert out["ok"] is True
    assert out["playbooks"]
    assert "login" in out["playbooks"][0]["body"].lower() or "Login" in out["playbooks"][0]["title"]


def test_lookup_miss():
    out = lookup_playbook("zzzz_no_such_playbook_zzzz")
    assert out["ok"] is False
    assert out["error"] == "no_match"
