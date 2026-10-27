import uuid

import requests

from clients.ai.anthropic_messages import AnthropicMessagesClient
from clients.ai.base import AiError, parse_model_list
from clients.ai.openai_chat import OpenAIChatClient
from clients.ai.openai_responses import OpenAIResponsesClient

BASE_URL = "https://opencode.ai/inference/go"
ANTHROPIC_MODELS = {
    "claude-haiku-5-5",
    "minimax-m3",
    "minimax-m2.7",
    "qwen3.8-max",
    "qwen3.8-flash",
    "qwen3.7-plus",
}
RESPONSES_MODELS = {
    "gpt-6-luna",
    "gpt-5.6-luna",
    "grok-4.7",
    "grok-4.6",
    "muse-spark-1.3-contributor",
    "muse-spark-1.2-contributor",
}
SESSION_ID = str(uuid.uuid4())


class OpenCodeGoClient:
    def __init__(self, model: str, api_key: str) -> None:
        if not api_key:
            raise AiError("Не задан API-ключ OpenCode Go")
        self.model = model
        self.api_key = api_key
        headers = {
            "User-Agent": "WorkAssistant/1.0",
            "x-opencode-session": SESSION_ID,
        }
        self._extra_headers = headers
        if model in ANTHROPIC_MODELS:
            self.base_url = f"{BASE_URL}/anthropic/v1"
            self._client = AnthropicMessagesClient(
                self.base_url,
                model,
                api_key,
                extra_headers=headers,
                use_bearer=False,
            )
        elif model in RESPONSES_MODELS:
            self.base_url = f"{BASE_URL}/openai/v1"
            self._client = OpenAIResponsesClient(
                self.base_url, model, api_key, extra_headers=headers
            )
        else:
            self.base_url = f"{BASE_URL}/openai/v1"
            self._client = OpenAIChatClient(
                self.base_url, model, api_key, extra_headers=headers
            )

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return self._client.complete_json(system_prompt, user_prompt)

    def list_models(self) -> list[str]:
        try:
            response = requests.get(
                f"{BASE_URL}/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise AiError(f"Неожиданный ответ списка моделей: {exc}") from exc
        return parse_model_list(payload)

    def check_connection(self) -> None:
        url, headers, body = self._probe_request()
        try:
            response = requests.post(
                url, headers=headers, json=body, timeout=30
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if response.status_code in (401, 403):
            raise AiError("Неверный API-ключ OpenCode Go")
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:200]}")

    def _probe_request(self) -> tuple[str, dict[str, str], dict]:
        if self.model in ANTHROPIC_MODELS:
            return (
                f"{BASE_URL}/anthropic/v1/messages",
                {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                    **self._extra_headers,
                },
                {
                    "model": self.model,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "ping"}],
                },
            )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }
        if self.model in RESPONSES_MODELS:
            return (
                f"{BASE_URL}/openai/v1/responses",
                headers,
                {
                    "model": self.model,
                    "input": "ping",
                    "max_output_tokens": 1,
                },
            )
        return (
            f"{BASE_URL}/openai/v1/chat/completions",
            headers,
            {
                "model": self.model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            },
        )
