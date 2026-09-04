from mango_studio_host.api_vault import lookup_api, load_vault


def test_vault_loads():
    cards = load_vault()
    assert len(cards) >= 5
    titles = {c["title"] for c in cards}
    assert "RemoteEvent" in titles or any("Remote" in t for t in titles)


def test_lookup_remote():
    result = lookup_api("RemoteEvent")
    assert result["ok"] is True
    assert result["cards"]
    assert "Remote" in result["cards"][0]["title"] or "Remote" in result["cards"][0]["body"]


def test_lookup_miss():
    result = lookup_api("zzzz_not_a_real_api_zzzz")
    assert result["ok"] is False
    assert result["error"] == "no_match"
