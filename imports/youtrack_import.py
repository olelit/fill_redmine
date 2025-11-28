import requests
from datetime import datetime, timedelta
from typing import List
from configs.config import Config
from dto.date_hours_dto import DateHoursDTO
from imports.base_importer import BaseImporter


class YoutrackImporter(BaseImporter):

    def create_record_list(self) -> List[DateHoursDTO]:
        youtrack_url = Config.get_youtrack_base_url()
        iterable_dto = Config.get_iterable_import_env(self.postfix)
        youtrack_token = iterable_dto.youtrack_access_token
        now = datetime.now()
        first_day = datetime(now.year, now.month, 1)

        if now.month == 12:
            last_day = datetime(now.year, 12, 31)
        else:
            first_day_next_month = datetime(now.year, now.month + 1, 1)
            last_day = first_day_next_month - timedelta(days=1)

        params = {
            "fields": "date,duration(minutes)",
            "start": int(first_day.timestamp() * 1000),
            "end": int(last_day.timestamp() * 1000),
            "$top": 500,
            "author": "me",
        }

        headers = {
            "Authorization": f"Bearer {youtrack_token}"
        }

        url = f"{youtrack_url}/api/workItems"
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        result = {}
        for item in data:
            date = datetime.fromtimestamp(item['date'] / 1000).strftime("%Y-%m-%d")

            if date not in result:
                result[date] = 0

            result[date] += item['duration']['minutes'] / 60

        dto_list: list[DateHoursDTO] = [
            DateHoursDTO(date=d, hours=h) for d, h in result.items()
        ]

        return dto_list
