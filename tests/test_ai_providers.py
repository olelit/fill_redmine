from unittest.mock import MagicMock, patch

import pytest
import requests

from clients.ai.base import AiError, parse_json_object
from clients.ai.factory import create_ai_client
from clients.ai.openai_chat import OpenAIChatClient
from clients.ai.openai_responses import OpenAIResponsesClient
from clients.ai.opencode_go import (
    ANTHROPIC_MODELS,
    BASE_URL,
    RESPONSES_MODELS,
    OpenCodeGoClient,
)
from configs.ai_settings import AiSettings


def response(payload: object, status: int = 200) -> MagicMock:
    result = MagicMock()
    result.status_code = status
    result.json.return_value = payload
    result.text = str(payload)
    return result


def broken_json_response(status: int = 200) -> MagicMock:
    result = MagicMock()
    result.status_code = status
    result.json.side_effect = ValueError("Expecting value")
    result.text = "not json"
    return result


def test_parse_json_object_with_fence():
    assert parse_json_object('```json\n{"summary": "ok"}\n```') == {"summary": "ok"}


def test_parse_json_object_tolerates_trailing_prose():
    text = 'Here you go: {"summary": "ok"} — hope that helps.'
    assert parse_json_object(text) == {"summary": "ok"}


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


def test_openai_chat_network_error_raises_ai_error():
    client = OpenAIChatClient("https://api.openai.com/v1", "gpt", "key")
    with patch(
        "clients.ai.openai_chat.requests.post",
        side_effect=requests.ConnectionError("boom"),
    ):
        with pytest.raises(AiError):
            client.complete_json("system", "user")


def test_openai_chat_http_500_raises_ai_error():
    client = OpenAIChatClient("https://api.openai.com/v1", "gpt", "key")
    with patch(
        "clients.ai.openai_chat.requests.post",
        return_value=response({"error": "boom"}, status=500),
    ):
        with pytest.raises(AiError, match="HTTP 500"):
            client.complete_json("system", "user")


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


def test_anthropic_messages_empty_content_raises_ai_error():
    client = create_ai_client(
        AiSettings(provider="anthropic", model="claude", keys={"anthropic": "key"})
    )
    with patch(
        "clients.ai.anthropic_messages.requests.post",
        return_value=response({"content": []}),
    ):
        with pytest.raises(AiError, match="пустой ответ"):
            client.complete_json("system", "user")


def test_openai_responses_complete_json():
    client = OpenAIResponsesClient("https://api.openai.com/v1", "gpt", "key")
    with patch(
        "clients.ai.openai_responses.requests.post",
        return_value=response({"output_text": '{"summary": "ok"}'}),
    ) as post:
        result = client.complete_json("system", "user")

    assert result == {"summary": "ok"}
    assert post.call_args.args[0] == "https://api.openai.com/v1/responses"
    body = post.call_args.kwargs["json"]
    assert body["instructions"] == "system"
    assert body["input"] == "user"


def test_openai_responses_falls_back_to_output_items():
    client = OpenAIResponsesClient("https://api.openai.com/v1", "gpt", "key")
    payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": '{"summary": "ok"}'}
                ]
            }
        ]
    }
    with patch(
        "clients.ai.openai_responses.requests.post",
        return_value=response(payload),
    ):
        assert client.complete_json("system", "user") == {"summary": "ok"}


def test_openai_responses_empty_output_raises_ai_error():
    client = OpenAIResponsesClient("https://api.openai.com/v1", "gpt", "key")
    with patch(
        "clients.ai.openai_responses.requests.post",
        return_value=response({"output": []}),
    ):
        with pytest.raises(AiError, match="пустой ответ"):
            client.complete_json("system", "user")


def test_list_models_non_json_raises_ai_error():
    client = OpenAIChatClient("https://api.openai.com/v1", "gpt", "key")
    with patch(
        "clients.ai.openai_chat.requests.get",
        return_value=broken_json_response(),
    ):
        with pytest.raises(AiError):
            client.list_models()


def test_list_models_null_data_raises_ai_error():
    client = OpenAIChatClient("https://api.openai.com/v1", "gpt", "key")
    with patch(
        "clients.ai.openai_chat.requests.get",
        return_value=response({"data": None}),
    ):
        with pytest.raises(AiError, match="списка моделей"):
            client.list_models()


def test_list_models_sorted_ids():
    client = OpenAIChatClient("https://api.openai.com/v1", "gpt", "key")
    with patch(
        "clients.ai.openai_chat.requests.get",
        return_value=response(
            {"data": [{"id": "b"}, {"id": "a"}, {"nope": 1}, "junk"]}
        ),
    ):
        assert client.list_models() == ["a", "b"]


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


def test_opencode_go_unknown_model_routes_to_chat():
    client = create_ai_client(
        AiSettings(
            provider="opencode_go", model="some-new-model", keys={"opencode_go": "key"}
        )
    )

    assert client.base_url.endswith("/openai/v1")
    assert isinstance(client._client, OpenAIChatClient)


@pytest.mark.parametrize(
    ("model", "path", "auth_header"),
    [
        (next(iter(ANTHROPIC_MODELS)), "/anthropic/v1/messages", "x-api-key"),
        (next(iter(RESPONSES_MODELS)), "/openai/v1/responses", "Authorization"),
        (
            "deepseek-v4.1-flash",
            "/openai/v1/chat/completions",
            "Authorization",
        ),
    ],
)
def test_opencode_go_check_connection_uses_authenticated_post(
    model: str, path: str, auth_header: str
) -> None:
    client = OpenCodeGoClient(model, "key")
    with patch(
        "clients.ai.opencode_go.requests.post", return_value=response({})
    ) as post:
        client.check_connection()

    assert post.call_args.args[0] == f"{BASE_URL}{path}"
    assert post.call_args.kwargs["headers"][auth_header]
    assert post.call_args.kwargs["json"]["model"] == model


def test_opencode_go_check_connection_rejects_unauthorized() -> None:
    client = OpenCodeGoClient("deepseek-v4.1-flash", "key")
    with patch(
        "clients.ai.opencode_go.requests.post",
        return_value=response({}, status=401),
    ):
        with pytest.raises(AiError, match="Неверный API-ключ"):
            client.check_connection()


def test_opencode_go_check_connection_http_error() -> None:
    client = OpenCodeGoClient("deepseek-v4.1-flash", "key")
    with patch(
        "clients.ai.opencode_go.requests.post",
        return_value=response({"error": "boom"}, status=500),
    ):
        with pytest.raises(AiError, match="HTTP 500"):
            client.check_connection()


def test_missing_key_raises():
    with pytest.raises(AiError, match="ключ"):
        create_ai_client(AiSettings(provider="openai", model="gpt"))


def test_unknown_provider_raises_before_model_check():
    with pytest.raises(AiError, match="Неизвестный AI-провайдер"):
        create_ai_client(AiSettings(provider="nope"))


def test_provider_is_normalized():
    client = create_ai_client(
        AiSettings(provider=" OpenAI ", model="gpt", keys={"openai": "key"})
    )

    assert isinstance(client, OpenAIChatClient)


def test_custom_requires_base_url_before_key():
    with pytest.raises(AiError, match="base_url"):
        create_ai_client(AiSettings(provider="custom", model="m"))
