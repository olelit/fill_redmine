from abc import ABC, abstractmethod
from collections.abc import Callable

from clients.redmine_client import RedmineClient
from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO


class BaseImporter(ABC):
    def __init__(self, project: ProjectConfig):
        self.project = project

    def redmine_config(self) -> dict:
        config = self.project.trackers.get("redmine", {})
        missing = [
            key
            for key in ("api_key", "user_id", "issue_id", "activity_id")
            if config.get(key) in (None, "")
        ]
        if missing:
            raise ValueError("Redmine не настроен: " + ", ".join(missing))
        return config

    def youtrack_token(self) -> str:
        token = self.project.trackers.get("youtrack", {}).get(
            "access_token", ""
        )
        if not token:
            raise ValueError("YouTrack не настроен: access_token")
        return token

    @abstractmethod
    def create_record_list(self) -> list[DateHoursDTO]:
        pass

    async def handle(
        self,
        records: list[DateHoursDTO] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[tuple[str, str]]:
        if records is None:
            records = self.create_record_list()

        config = self.redmine_config()
        return await self.update_redmine_activity(
            uid=int(config["user_id"]),
            iid=int(config["issue_id"]),
            comment=config.get("comment", ""),
            activity_id=int(config["activity_id"]),
            api_key=config["api_key"],
            records=records,
            on_progress=on_progress,
        )

    async def update_redmine_activity(
        self,
        uid: int,
        iid: int,
        comment: str,
        activity_id: int,
        api_key: str,
        records: list[DateHoursDTO],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[tuple[str, str]]:
        client = RedmineClient(api_key=api_key)
        return await client.create_time_entries(
            user_id=uid,
            issue_id=iid,
            comment=comment,
            activity_id=activity_id,
            records=records,
            on_progress=on_progress,
        )
