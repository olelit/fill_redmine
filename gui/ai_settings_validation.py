from configs.ai_settings import AiSettings

PROVIDERS = ("opencode_go", "openai", "anthropic", "custom")


def request_is_current(
    token: str,
    seq: int,
    current_token: str,
    current_seq: int | None,
) -> bool:
    return token == current_token and seq == current_seq


def validate_ai_settings(
    provider: str,
    model: str,
    base_url: str,
    keys: dict[str, str],
) -> tuple[AiSettings | None, list[str]]:
    errors: list[str] = []
    if provider not in PROVIDERS:
        errors.append("Неизвестный провайдер")
    if not model.strip():
        errors.append("Выберите модель")
    if not keys.get(provider, "").strip():
        errors.append(f"Не задан API-ключ для {provider}")
    if provider == "custom" and not base_url.strip():
        errors.append("Для custom нужен base_url")
    if errors:
        return None, errors
    return (
        AiSettings(
            provider=provider,
            model=model.strip(),
            base_url=base_url.strip(),
            keys={k: v.strip() for k, v in keys.items() if v.strip()},
        ),
        [],
    )
