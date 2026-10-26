from unittest.mock import MagicMock, patch

import pytest

from clients.ai_client import (
    AiClient,
    AiConfig,
    AiError,
    parse_json_object,
    resolve_ai_config,
)
from configs.project_config import ProjectConfig


def test_project_settings_override_env(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    project = ProjectConfig(
        name="P",
        ai={
            "base_url": "https://project.example/v1",
            "model": "project-model",
            "api_key": "project-key",
        },
    )

    config = resolve_ai_config(project)

    assert config == AiConfig(
        base_url="https://project.example/v1",
        model="project-model",
        api_key="project-key",
    )


def test_env_fallback_and_default_base_url(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")

    config = resolve_ai_config(ProjectConfig(name="P"))

    assert config.base_url == "https://api.openai.com/v1"
    assert config.model == "env-model"
    assert config.api_key == "env-key"


def test_missing_model_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "key")

    with pytest.raises(AiError, match="модель"):
        resolve_ai_config(ProjectConfig(name="P"))


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "model")

    with pytest.raises(AiError, match="ключ"):
        resolve_ai_config(ProjectConfig(name="P"))


def test_parse_json_with_markdown_fence():
    payload = parse_json_object('```json\n{"summary": "ok"}\n```')

    assert payload == {"summary": "ok"}


def test_complete_json_sends_request():
    client = AiClient(AiConfig("https://api.example/v1", "model", "key"))
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": '{"summary": "ok"}'}}]
    }

    with patch("clients.ai_client.requests.post", return_value=response) as post:
        result = client.complete_json("system", "user")

    assert result == {"summary": "ok"}
    body = post.call_args.kwargs["json"]
    assert body["model"] == "model"
    assert body["messages"][0]["content"] == "system"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer key"


def test_http_error_raises():
    client = AiClient(AiConfig("https://api.example/v1", "model", "key"))
    response = MagicMock()
    response.status_code = 500
    response.text = "boom"

    with patch("clients.ai_client.requests.post", return_value=response):
        with pytest.raises(AiError, match="500"):
            client.complete_json("system", "user")


def test_invalid_json_raises():
    client = AiClient(AiConfig("https://api.example/v1", "model", "key"))
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": "not-json"}}]
    }

    with patch("clients.ai_client.requests.post", return_value=response):
        with pytest.raises(AiError, match="JSON"):
            client.complete_json("system", "user")
