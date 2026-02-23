from dataclasses import dataclass, field


MANUAL = "manual"
YOUTRACK = "youtrack"


@dataclass
class UserConfig:
    is_enable: bool
    name: str
    redmine_api_key: str
    user_id: int
    activity_id: int
    comment: str
    issue_id: int
    driver: str
    youtrack_access_token: str
    exclude_dates: list[str] = field(default_factory=list)

    def is_manual(self) -> bool:
        return self.driver == MANUAL

    def is_youtrack(self) -> bool:
        return self.driver == YOUTRACK
