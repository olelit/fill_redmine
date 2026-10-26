from dataclasses import dataclass, field


@dataclass
class DayPlanDTO:
    date: str
    existing_hours: float
    deficit_hours: float
    planned_hours: float
    comment: str = ""
    commit_hashes: list[str] = field(default_factory=list)
    confidence: str = "low"


@dataclass
class CommitPlanDTO:
    summary: str
    days: list[DayPlanDTO]
    raw_response: str = ""
