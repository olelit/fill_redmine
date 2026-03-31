from abc import ABC, abstractmethod
from typing import List

from clients.redmine_client import RedmineClient
from configs.user_config import UserConfig
from dto.date_hours_dto import DateHoursDTO


class BaseImporter(ABC):
    def __init__(self, user: UserConfig):
        self.user = user

    @abstractmethod
    def create_record_list(self) -> List[DateHoursDTO]:
        pass

    async def handle(self):
        records = self.create_record_list()
        iid = self.user.issue_id
        uid = self.user.user_id
        comment = self.user.comment
        activity_id = self.user.activity_id
        api_key = self.user.redmine_api_key
        await self.update_redmine_activity(
            uid, iid, comment, activity_id, api_key, records
        )

    async def update_redmine_activity(
        self,
        uid: int,
        iid: int,
        comment: str,
        activity_id: int,
        api_key: str,
        records: List[DateHoursDTO],
    ):
        client = RedmineClient(api_key=api_key)
        await client.create_time_entries(
            user_id=uid,
            issue_id=iid,
            comment=comment,
            activity_id=activity_id,
            records=records,
        )
