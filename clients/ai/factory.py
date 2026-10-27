from clients.ai.anthropic_messages import AnthropicMessagesClient
from clients.ai.base import AiClient, AiError
from clients.ai.openai_chat import OpenAIChatClient
from clients.ai.opencode_go import OpenCodeGoClient
from configs.ai_settings import AiSettings

PROVIDERS = ("opencode_go", "openai", "anthropic", "custom")


def create_ai_client(settings: AiSettings) -> AiClient:
    key = settings.key_for(settings.provider)
    if not settings.model:
        raise AiError("Не задана модель ИИ")
    if not key:
        raise AiError(f"Не задан API-ключ для {settings.provider}")
    if settings.provider == "opencode_go":
        return OpenCodeGoClient(settings.model, key)
    if settings.provider == "openai":
        return OpenAIChatClient("https://api.openai.com/v1", settings.model, key)
    if settings.provider == "anthropic":
        return AnthropicMessagesClient(
            "https://api.anthropic.com/v1", settings.model, key
        )
    if settings.provider == "custom":
        if not settings.base_url:
            raise AiError("Не задан base_url для custom-провайдера")
        return OpenAIChatClient(settings.base_url, settings.model, key)
    raise AiError(f"Неизвестный AI-провайдер: {settings.provider}")
