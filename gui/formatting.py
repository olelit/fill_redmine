from datetime import date

from dto.preview_dto import DateRangeDTO


def format_hours(hours: int | float) -> str:
    return f"{hours:g}"


def format_range(rng: DateRangeDTO) -> str:
    start = date.fromisoformat(rng.start_date).strftime("%d.%m")
    end = date.fromisoformat(rng.end_date).strftime("%d.%m")
    if rng.start_date == rng.end_date:
        return f"{start} — {format_hours(rng.hours)}h"
    return f"{start}–{end} — {format_hours(rng.hours)}h"


def format_ranges(ranges: list[DateRangeDTO]) -> str:
    return "; ".join(format_range(rng) for rng in ranges)
