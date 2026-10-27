from unittest.mock import MagicMock, patch

import pytest

from clients.ai.base import AiError, parse_json_object
from clients.ai.factory import create_ai_client
from clients.ai.opencode_go import ANTHROPIC_MODELS, RESPONSES_MODELS
from configs.ai_settings import AiSettings


def response(payload, status=200):
    result = MagicMock()
    result.status_code = status
    result.json.return_value = payload
    result.text = str(payload)
    return result


def test_parse_json_object_with_fence():
    assert parse_json_object('```json\n{"summary": "ok"}\n```') == {"summary": "ok"}


def test_openai_chat_complete_json():
    settings = AiSettings(
        provider="openai", model="gpt", keys={"openai": "key"}
    )
    client = create_ai_client(settings)
    with patch(
        "clients.ai.openai_chat.requests.post",
        return_value=response(
            {"choices": [{"message": {"content": '{"summary": "ok"}'}}]}
        ),
    ) as post:
        result = client.complete_json("system", "user")

    assert result == {"summary": "ok"}
    assert post.call_args.args[0] == "https://api.openai.com/v1/chat/completions"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer key"


def test_anthropic_messages_complete_json():
    settings = AiSettings(
        provider="anthropic", model="claude", keys={"anthropic": "key"}
    )
    client = create_ai_client(settings)
    with patch(
        "clients.ai.anthropic_messages.requests.post",
        return_value=response(
            {"content": [{"type": "text", "text": '{"summary": "ok"}'}]}
        ),
    ) as post:
        result = client.complete_json("system", "user")

    assert result == {"summary": "ok"}
    assert post.call_args.args[0] == "https://api.anthropic.com/v1/messages"
    assert post.call_args.kwargs["headers"]["x-api-key"] == "key"


def test_opencode_go_routes_anthropic_models():
    settings = AiSettings(
        provider="opencode_go",
        model=next(iter(ANTHROPIC_MODELS)),
        keys={"opencode_go": "key"},
    )
    client = create_ai_client(settings)

    assert client.base_url.endswith("/anthropic/v1")


def test_opencode_go_routes_responses_models():
    settings = AiSettings(
        provider="opencode_go",
        model=next(iter(RESPONSES_MODELS)),
        keys={"opencode_go": "key"},
    )
    client = create_ai_client(settings)

    assert client.base_url.endswith("/openai/v1")


def test_missing_key_raises():
    with pytest.raises(AiError, match="ключ"):
        create_ai_client(AiSettings(provider="openai", model="gpt"))
