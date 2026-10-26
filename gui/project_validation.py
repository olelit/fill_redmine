from datetime import date

from configs.project_config import ProjectConfig
from trackers.registry import all_trackers


def _int_value(value, label: str, errors: list[str]) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        errors.append(f"{label}: должно быть целым числом")
        return 0
    if parsed <= 0:
        errors.append(f"{label}: должно быть больше нуля")
    return parsed


def validate_project_form(
    form: dict[str, str],
    exclude_dates: list[str],
    tracker_values: dict[str, dict],
    ai_values: dict[str, str],
    db_id: int | None = None,
) -> tuple[ProjectConfig | None, list[str]]:
    errors: list[str] = []
    name = form.get("name", "").strip()
    if not name:
        errors.append("Имя проекта обязательно")

    try:
        workday_hours = float(form.get("workday_hours", "8"))
    except (TypeError, ValueError):
        errors.append("Рабочий день: должно быть числом")
        workday_hours = 8.0
    if not 0 < workday_hours <= 24:
        errors.append("Рабочий день: должно быть больше 0 и не больше 24")

    trackers: dict[str, dict] = {}
    for cls in all_trackers():
        values = tracker_values.get(cls.kind, {})
        cls_errors = cls.validate_config(values)
        errors.extend(cls_errors)
        if cls_errors or not any(
            values.get(field.key) not in (None, "")
            for field in cls.fields
            if field.required
        ):
            continue
        config: dict = {}
        for field in cls.fields:
            raw = values.get(field.key, "")
            if raw in (None, ""):
                continue
            if field.kind == "int":
                config[field.key] = _int_value(raw, f"{cls.label}: {field.label}", errors)
            else:
                config[field.key] = str(raw).strip()
        trackers[cls.kind] = config

    ai = {
        key: value.strip()
        for key, value in ai_values.items()
        if value.strip()
    }
    base_url = ai.get("base_url", "")
    if base_url and not base_url.startswith(("http://", "https://")):
        errors.append("ИИ: base_url должен начинаться с http:// или https://")

    if errors:
        return None, errors

    return (
        ProjectConfig(
            name=name,
            git_repo_path=form.get("git_repo_path", "").strip(),
            git_author_email=form.get("git_author_email", "").strip(),
            workday_hours=workday_hours,
            exclude_dates=sorted(exclude_dates),
            trackers=trackers,
            ai=ai,
            db_id=db_id,
        ),
        [],
    )


def parse_period(start_text: str, end_text: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(start_text.strip())
        end = date.fromisoformat(end_text.strip())
    except ValueError as exc:
        raise ValueError("Даты должны быть в формате ГГГГ-ММ-ДД") from exc
    if start > end:
        raise ValueError("Начало периода позже конца")
    return start, end
