import json
import os
from dataclasses import dataclass

import requests

from configs.project_config import ProjectConfig


class AiError(RuntimeError):
    pass


@dataclass(frozen=True)
class AiConfig:
    base_url: str
    model: str
    api_key: str


def resolve_ai_config(project: ProjectConfig) -> AiConfig:
    base_url = str(
        project.ai.get("base_url")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = str(project.ai.get("model") or os.getenv("OPENAI_MODEL") or "")
    api_key = str(
        project.ai.get("api_key") or os.getenv("OPENAI_API_KEY") or ""
    )
    if not model:
        raise AiError("Не задана модель ИИ (model)")
    if not api_key:
        raise AiError("Не задан API-ключ ИИ (api_key)")
    return AiConfig(base_url=base_url, model=model, api_key=api_key)


def parse_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AiError("ИИ вернул ответ без JSON-объекта")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AiError(f"ИИ вернул невалидный JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AiError("ИИ вернул JSON не-объект")
    return parsed


class AiClient:
    def __init__(self, config: AiConfig):
        self.config = config

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        response = requests.post(
            f"{self.config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            },
            timeout=120,
        )
        if not 200 <= response.status_code < 300:
            raise AiError(
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AiError(f"Неожиданный ответ ИИ: {exc}") from exc
        return parse_json_object(content)
