from abc import ABC, abstractmethod
from collections.abc import Callable

from clients.redmine_client import RedmineClient
from configs.user_config import UserConfig
from dto.date_hours_dto import DateHoursDTO


class BaseImporter(ABC):
    def __init__(self, user: UserConfig):
        self.user = user

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

        return await self.update_redmine_activity(
            self.user.user_id,
            self.user.issue_id,
            self.user.comment,
            self.user.activity_id,
            self.user.redmine_api_key,
            records,
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
