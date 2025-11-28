import asyncio
import os
from abc import ABC, abstractmethod
from typing import List

import aiohttp

from dto.date_hours_dto import DateHoursDTO


class BaseImporter(ABC):

    def __init__(self, postfix: int):
        self.postfix = postfix

    @abstractmethod
    def create_record_list(self) -> List[DateHoursDTO]:
        pass

    async def run(self):
        records = self.create_record_list()
        iid = int(os.getenv(f"ISSUE_ID_{self.postfix}"))
        uid = int(os.getenv(f"USER_ID_{self.postfix}"))
        comment = os.getenv(f"COMMENT_{self.postfix}")
        activity_id = int(os.getenv(f"ACTIVITY_ID_{self.postfix}"))
        api_key = os.getenv(f"REDMINE_API_KEY_{self.postfix}")
        await self.update_redmine_activity(uid, iid, comment, activity_id, api_key, records)
        pass

    async def update_redmine_activity(self, uid: int, iid: int, comment: str, activity_id: int, api_key: str, records: List[DateHoursDTO]):
        redmine_url = os.getenv('REDMINE_BASE_URL')
        url = f"{redmine_url}/time_entries.xml"
        headers = {
            "Content-Type": "application/xml",
            "X-Redmine-API-Key": api_key
        }

        print("The following dates will be affected:")
        hour_sum = 0
        for dateHourDTO in records:
            hours = dateHourDTO.hours
            print(f"{dateHourDTO.date} - {hours}h")
            hour_sum += hours
        print(f"Comment: {comment}")
        print(f"Total hours: {hour_sum}")

        proceed = input("Do you want to continue? (y/n): ").strip().lower()
        if proceed != "y":
            print("Script execution stopped by the user.")
            return

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
