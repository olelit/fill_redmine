import json
from typing import Protocol


class AiError(RuntimeError):
    pass


class AiClient(Protocol):
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict: ...
    def list_models(self) -> list[str]: ...
    def check_connection(self) -> None: ...


def parse_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise AiError("ИИ вернул ответ без JSON-объекта")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AiError(f"ИИ вернул невалидный JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AiError("ИИ вернул JSON не-объект")
    return parsed
