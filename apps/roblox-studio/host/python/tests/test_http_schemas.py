from pydantic import ValidationError

from mango_studio_host.schemas import RunBody, StudioCallBody, validation_error_body


def test_run_body_defaults():
    body = RunBody.model_validate({})
    assert body.session_id == "studio"
    assert body.mode == "roblox"


def test_studio_call_requires_tool():
    try:
        StudioCallBody.model_validate({"tool": ""})
        assert False, "expected ValidationError"
    except ValidationError as exc:
        payload = validation_error_body(exc)
        assert payload["error"] == "invalid_payload"
        assert payload["detail"]
