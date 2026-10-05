from dataclasses import dataclass, field


@dataclass
class DateRangeDTO:
    start_date: str
    end_date: str
    hours: int | float


@dataclass
class PreviewDTO:
    user_name: str
    user_id: int
    driver: str
    comment: str
    issue_id: int
    issue_subject: str | None = None
    issue_url: str | None = None
    issue_author: str | None = None
    issue_created_on: str | None = None
    ranges: list[DateRangeDTO] = field(default_factory=list)
    total_hours: float = 0
    error: str | None = None
