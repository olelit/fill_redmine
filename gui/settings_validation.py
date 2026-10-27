from configs.project_config import ProjectConfig, ProjectUserConfig
from trackers.registry import all_trackers


def validate_project_settings(
    form: dict[str, str], exclude_dates: list[str]
) -> tuple[ProjectConfig | None, list[str]]:
    errors: list[str] = []
    try:
        workday = float(form.get("workday_hours", "8"))
    except (TypeError, ValueError):
        errors.append("Рабочий день: должно быть числом")
        workday = 8.0
    if not 0 < workday <= 24:
        errors.append("Рабочий день: больше 0 и не больше 24")
    comment = form.get("default_comment", "development").strip()
    if not comment:
        errors.append("Комментарий по умолчанию обязателен")
    if errors:
        return None, errors
    return (
        ProjectConfig(
            name="",
            git_repo_path=form.get("git_repo_path", "").strip(),
            workday_hours=workday,
            exclude_dates=sorted(exclude_dates),
            default_comment=comment,
        ),
        [],
    )


def _int_value(value: object, label: str, errors: list[str]) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        errors.append(f"{label}: должно быть целым числом")
        return 0
    if parsed <= 0:
        errors.append(f"{label}: должно быть больше нуля")
    return parsed


def validate_user_settings(
    name: str,
    git_email: str,
    tracker_values: dict[str, dict],
) -> tuple[ProjectUserConfig | None, list[str]]:
    errors: list[str] = []
    name = name.strip()
    if not name:
        errors.append("Имя юзера обязательно")
    if git_email and "@" not in git_email:
        errors.append("git email выглядит некорректно")

    trackers: dict[str, dict] = {}
    for cls in all_trackers():
        values = tracker_values.get(cls.kind, {})
        cls_errors = cls.validate_config(values)
        errors.extend(cls_errors)
        if cls_errors:
            continue
        if not any(
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

    if errors:
        return None, errors
    return (
        ProjectUserConfig(
            name=name,
            git_email=git_email.strip(),
            trackers=trackers,
        ),
        [],
    )


def duplicate_user_names(users: list[ProjectUserConfig]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for user in users:
        name = user.name.strip()
        if not name:
            continue
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    return duplicates
