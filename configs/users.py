from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserConfig:
    is_enable: bool
    redmine_api_key: str
    user_id: int
    activity_id: int
    comment: str
    issue_id: int
    source: str
    youtrack_access_token: str
    exclude_dates: list[str] = field(default_factory=list)
    name: Optional[str] = None


USERS = [
    UserConfig(
        is_enable=True,
        redmine_api_key="153ba5e49bff60aec3fe679d7cc643e719b21409",
        user_id=16,
        activity_id=9,
        comment="development",
        issue_id=2535,
        source="youtrack",
        youtrack_access_token="perm-T2xlZy5MaXRhc292.NTMtNQ==.2zByrlpSvAoHqaSHwi4F004phV5h4a",
        exclude_dates=[],
    ),
]
