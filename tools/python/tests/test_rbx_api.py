from mango_tools.implementations.rbx_api import rbx_api


def test_rbx_api_remote():
    out = rbx_api("TweenService")
    assert out.get("ok") is True
    assert out.get("cards")
