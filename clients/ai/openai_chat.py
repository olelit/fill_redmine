import requests

from clients.ai.base import AiError, parse_json_object


class OpenAIChatClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.extra_headers = extra_headers or {}

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AiError(f"Неожиданный ответ ИИ: {exc}") from exc
        if not isinstance(content, str):
            raise AiError("ИИ вернул пустой ответ")
        return parse_json_object(content)

    def list_models(self) -> list[str]:
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
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
