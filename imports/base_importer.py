import asyncio
from abc import ABC, abstractmethod
from typing import List

import aiohttp

from configs.config import Config
from configs.user_config import UserConfig
from dto.date_hours_dto import DateHoursDTO


class BaseImporter(ABC):

    def __init__(self, user: UserConfig):
        self.user = user

    @abstractmethod
    def create_record_list(self) -> List[DateHoursDTO]:
        pass

    async def run(self):
        records = self.create_record_list()
        iid = self.user.issue_id
        uid = self.user.user_id
        comment = self.user.comment
        activity_id = self.user.activity_id
        api_key = self.user.redmine_api_key
        await self.update_redmine_activity(uid, iid, comment, activity_id, api_key, records)

    async def update_redmine_activity(self, uid: int, iid: int, comment: str, activity_id: int, api_key: str, records: List[DateHoursDTO]):
        redmine_url = Config.get_redmine_base_url()
        url = f"{redmine_url}/time_entries.xml"
        headers = {
            "Content-Type": "application/xml",
            "X-Redmine-API-Key": api_key
        }

        async with aiohttp.ClientSession() as session:
            tasks = []

            for dateHourDTO in records:
                    tasks.append(self.set_time(session, url, headers, iid, uid, dateHourDTO.date, dateHourDTO.hours, activity_id, comment))
            await asyncio.gather(*tasks)

    async def set_time(self, session, url, headers, iid, uid, day, hours, activity_id, comments):
        body = f"""
    <time_entry>
      <issue_id>{iid}</issue_id>
      <user_id>{uid}</user_id>
      <spent_on>{day}</spent_on>
      <hours>{hours}</hours>
      <activity_id>{activity_id}</activity_id>
      <comments>{comments}</comments>
    </time_entry>
    """.strip()
        async with session.post(url, headers=headers, data=body) as response:
            text = await response.text()
            if 200 <= response.status < 300:
                print(f"OK: {day}")
            else:
                print(f"ERROR: {day} {response.status} {text}")
