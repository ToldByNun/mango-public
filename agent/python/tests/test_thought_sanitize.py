from mango_agent.thought_sanitize import is_empty_thought, strip_thought_markup

RT_OPEN = "<" + "redacted_thinking" + ">"
RT_CLOSE = "</" + "redacted_thinking" + ">"
TH_OPEN = "<" + "think" + ">"
TH_CLOSE = "</" + "think" + ">"


def test_strip_redacted_thinking_wrappers() -> None:
    assert strip_thought_markup("Hello world") == "Hello world"
    assert strip_thought_markup(f"{RT_OPEN}{RT_CLOSE}") == ""
    assert strip_thought_markup(f"{RT_OPEN} inner text {RT_CLOSE}") == "inner text"
    assert strip_thought_markup(f"{RT_OPEN} stray open") == "stray open"


def test_strip_classic_think_tags() -> None:
    assert strip_thought_markup(f"{TH_OPEN}classic{TH_CLOSE}") == "classic"
    assert strip_thought_markup(f"{TH_OPEN} {TH_CLOSE}") == ""


def test_strip_partial_tags_at_end() -> None:
    assert strip_thought_markup(f"partial {RT_OPEN}") == "partial"
    assert strip_thought_markup(f"partial {RT_CLOSE[:4]}") == "partial"


def test_is_empty_thought() -> None:
    assert is_empty_thought(f"{RT_OPEN}   {RT_CLOSE}")
    assert not is_empty_thought("real prose")


def test_strip_drops_api_dump_tail() -> None:
    raw = "Need csv reader. csv.reader(source) | docs | read"
    assert strip_thought_markup(raw) == "Need csv reader."
