from datetime import date


class PeriodError(ValueError):
    """Raised when a requested period is invalid."""


def default_period(today: date) -> tuple[date, date]:
    return today.replace(day=1), today


def parse_period(
    start: str | None, end: str | None, today: date | None = None
) -> tuple[date, date]:
    current = date.today() if today is None else today
    default_start, default_end = default_period(current)
    start_date = _parse_date(start) if start is not None else default_start
    end_date = _parse_date(end) if end is not None else default_end
    if start_date > end_date:
        raise PeriodError("Start date must not be after end date")
    return start_date, end_date


def _parse_date(raw: str) -> date:
    try:
        value = date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise PeriodError(
            "Dates must use YYYY-MM-DD ISO format"
        ) from None
    if value.isoformat() != raw:
        raise PeriodError("Dates must use YYYY-MM-DD ISO format")
    return value