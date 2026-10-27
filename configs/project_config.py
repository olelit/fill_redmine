from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectUserConfig:
    name: str
    git_email: str = ""
    trackers: dict[str, dict[str, Any]] = field(default_factory=dict)
    project_id: int | None = None
    db_id: int | None = None


@dataclass
class ProjectConfig:
    name: str
    git_repo_path: str = ""
    git_author_email: str = ""  # legacy
    workday_hours: float = 8.0
    exclude_dates: list[str] = field(default_factory=list)
    default_comment: str = "development"
    users: list[ProjectUserConfig] = field(default_factory=list)
    trackers: dict[str, dict[str, Any]] = field(default_factory=dict)  # legacy
    ai: dict[str, Any] = field(default_factory=dict)  # legacy
    db_id: int | None = None

    def tracker(self, kind: str) -> dict[str, Any]:
        return self.trackers.get(kind, {})

    def user_by_id(self, db_id: int) -> ProjectUserConfig | None:
        for user in self.users:
            if user.db_id == db_id:
                return user
        return None
