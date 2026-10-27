import requests

from clients.ai.base import AiError, parse_json_object


class AnthropicMessagesClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
        use_bearer: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.extra_headers = extra_headers or {}
        self.use_bearer = use_bearer

    def _headers(self) -> dict[str, str]:
        auth = (
            {"Authorization": f"Bearer {self.api_key}"}
            if self.use_bearer
            else {"x-api-key": self.api_key}
        )
        return {
            **auth,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        try:
            response = requests.post(
                f"{self.base_url}/messages",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        try:
            parts = response.json()["content"]
            text = "".join(
                part.get("text", "")
                for part in parts
                if part.get("type") == "text"
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AiError(f"Неожиданный ответ ИИ: {exc}") from exc
        return parse_json_object(text)

    def list_models(self) -> list[str]:
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=30,
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        data = response.json().get("data", [])
        return sorted(str(item["id"]) for item in data if "id" in item)

    def check_connection(self) -> None:
        self.list_models()
