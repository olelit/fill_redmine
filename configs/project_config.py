from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectConfig:
    name: str
    git_repo_path: str = ""
    git_author_email: str = ""
    workday_hours: float = 8.0
    exclude_dates: list[str] = field(default_factory=list)
    trackers: dict[str, dict[str, Any]] = field(default_factory=dict)
    ai: dict[str, Any] = field(default_factory=dict)
    db_id: int | None = None

    def tracker(self, kind: str) -> dict[str, Any]:
        return self.trackers.get(kind, {})
