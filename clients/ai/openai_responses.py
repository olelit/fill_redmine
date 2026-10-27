import requests

from clients.ai.base import AiError, parse_json_object


class OpenAIResponsesClient:
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
                f"{self.base_url}/responses",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "instructions": system_prompt,
                    "input": user_prompt,
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        payload = response.json()
        text = payload.get("output_text")
        if not text:
            parts: list[str] = []
            for item in payload.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        parts.append(content.get("text", ""))
            text = "".join(parts)
        if not text:
            raise AiError("ИИ вернул пустой ответ")
        return parse_json_object(text)

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
