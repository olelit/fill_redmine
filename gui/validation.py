from datetime import date

from configs.user_config import MANUAL, YOUTRACK, UserConfig


def parse_positive_int(value: str, label: str, errors: list[str]) -> int:
    try:
        parsed = int(value.strip())
    except (TypeError, ValueError):
        errors.append(f"{label}: должно быть целым числом")
        return 0
    if parsed <= 0:
        errors.append(f"{label}: должно быть больше нуля")
    return parsed


def validate_user_form(
    form: dict[str, str],
    is_enable: bool,
    exclude_dates: list[str],
    db_id: int | None = None,
) -> tuple[UserConfig | None, list[str]]:
    errors: list[str] = []

    name = form.get("name", "").strip()
    if not name:
        errors.append("Имя обязательно")

    driver = form.get("driver", MANUAL)
    if driver not in (MANUAL, YOUTRACK):
        errors.append("Некорректный driver")

    token = form.get("youtrack_access_token", "").strip()
    if driver == YOUTRACK and not token:
        errors.append("Для youtrack нужен access_token")

    user_id = parse_positive_int(form.get("user_id", ""), "user_id", errors)
    activity_id = parse_positive_int(form.get("activity_id", ""), "activity_id", errors)
    issue_id = parse_positive_int(form.get("issue_id", ""), "issue_id", errors)

    if errors:
        return None, errors

    return (
        UserConfig(
            is_enable=is_enable,
            name=name,
            redmine_api_key=form.get("redmine_api_key", "").strip(),
            user_id=user_id,
            activity_id=activity_id,
            comment=form.get("comment", "").strip(),
            issue_id=issue_id,
            driver=driver,
            youtrack_access_token=token,
            exclude_dates=sorted(exclude_dates),
            db_id=db_id,
        ),
        [],
    )


def parse_exclude_date(value: str, existing: list[str]) -> tuple[str | None, str | None]:
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError:
        return None, "Дата должна быть в формате ГГГГ-ММ-ДД"

    iso = parsed.isoformat()
    if iso in existing:
        return None, "Дата уже добавлена"

    return iso, None
