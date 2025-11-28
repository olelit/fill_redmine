from dataclasses import dataclass

@dataclass
class IterableConfigDTO:
    redmine_api_key: str
    user_id: int
    activity_id: int
    comment: str
    issue_id: int
    source: str
    youtrack_access_token: str
    exclude_dates: str
