from gui.ai_settings_validation import request_is_current, validate_ai_settings


def test_valid_settings():
    settings, errors = validate_ai_settings(
        provider="openai",
        model="gpt",
        base_url="",
        keys={"openai": "key"},
    )
    assert errors == []
    assert settings.provider == "openai"
    assert settings.keys["openai"] == "key"


def test_openai_requires_key():
    settings, errors = validate_ai_settings(
        provider="openai", model="gpt", base_url="", keys={}
    )
    assert settings is None
    assert any("ключ" in error.lower() for error in errors)


def test_custom_requires_base_url():
    settings, errors = validate_ai_settings(
        provider="custom",
        model="model",
        base_url="",
        keys={"custom": "key"},
    )
    assert settings is None
    assert any("base_url" in error for error in errors)


def test_request_is_current():
    assert request_is_current("tok", 2, "tok", 2) is True
    assert request_is_current("other", 2, "tok", 2) is False
    assert request_is_current("tok", 1, "tok", 2) is False

