from datetime import date
from typing import Any


def validate_tracking_request(
    user_ids: list[int],
    destination: str,
    source: str,
    source_kind: str,
    start_text: str,
    end_text: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not user_ids:
        errors.append("Выберите хотя бы одного юзера")
    if not destination:
        errors.append("Выберите трекер-назначение")
    if not source:
        errors.append("Выберите источник")
    if source == "tracker":
        if not source_kind:
            errors.append("Выберите трекер-источник")
        elif source_kind == destination:
            errors.append("Источник и назначение не могут совпадать")
    try:
        start: date | None = date.fromisoformat(start_text.strip())
        end: date | None = date.fromisoformat(end_text.strip())
    except ValueError:
        errors.append("Даты должны быть в формате ГГГГ-ММ-ДД")
        start = end = None
    if start is not None and end is not None and start > end:
        errors.append("Начало периода позже конца")
    if errors:
        return None, errors
    return (
        {
            "user_ids": list(user_ids),
            "destination": destination,
            "source": source,
            "source_kind": source_kind,
            "start": start,
            "end": end,
        },
        [],
    )
