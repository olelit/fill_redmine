from clients.ai.anthropic_messages import AnthropicMessagesClient
from clients.ai.base import AiClient, AiError
from clients.ai.openai_chat import OpenAIChatClient
from clients.ai.opencode_go import OpenCodeGoClient
from configs.ai_settings import AiSettings

PROVIDERS = ("opencode_go", "openai", "anthropic", "custom")


def create_ai_client(settings: AiSettings) -> AiClient:
    provider = settings.provider.strip().lower()
    if provider not in PROVIDERS:
        raise AiError(f"Неизвестный AI-провайдер: {settings.provider}")
    key = settings.key_for(provider)
    if not settings.model:
        raise AiError("Не задана модель ИИ")
    if provider == "custom" and not settings.base_url:
        raise AiError("Не задан base_url для custom-провайдера")
    if not key:
        raise AiError(f"Не задан API-ключ для {settings.provider}")
    if provider == "opencode_go":
        return OpenCodeGoClient(settings.model, key)
    if provider == "openai":
        return OpenAIChatClient("https://api.openai.com/v1", settings.model, key)
    if provider == "anthropic":
        return AnthropicMessagesClient(
            "https://api.anthropic.com/v1", settings.model, key
        )
    return OpenAIChatClient(settings.base_url, settings.model, key)
