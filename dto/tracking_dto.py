from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class TrackingSource(str, Enum):
    AUTOFILL = "autofill"
    TRACKER = "tracker"
    COMMITS = "commits"


@dataclass
class TrackingRow:
    row_id: str
    user_id: int
    user_name: str
    date: str
    existing_hours: float
    proposed_hours: float
    comment: str
    source_details: str = ""
    include: bool = True
    status: str = ""
    error: str = ""


@dataclass
class TrackingReport:
    destination_kind: str
    source: TrackingSource
    source_kind: str = ""
    start: date | None = None
    end: date | None = None
    rows: list[TrackingRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class TrackingWriteResult:
    written: int = 0
    errors: list[tuple[str, str, str]] = field(default_factory=list)
