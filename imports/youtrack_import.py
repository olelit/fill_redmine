from datetime import datetime, timedelta
from typing import List

from clients.youtrack_client import YoutrackClient
from dto.date_hours_dto import DateHoursDTO
from imports.base_importer import BaseImporter


class YoutrackImporter(BaseImporter):
    def create_record_list(self) -> List[DateHoursDTO]:
        now = datetime.now()
        first_day = datetime(now.year, now.month, 1)

        if now.month == 12:
            last_day = datetime(now.year, 12, 31)
        else:
            first_day_next_month = datetime(now.year, now.month + 1, 1)
            last_day = first_day_next_month - timedelta(days=1)

        client = YoutrackClient(access_token=self.user.youtrack_access_token)
        data = client.get_work_items(start_date=first_day, end_date=last_day)
        result = {}
        for item in data:
            date = datetime.fromtimestamp(item["date"] / 1000).strftime("%Y-%m-%d")

            if date not in result:
                result[date] = 0

            result[date] += item["duration"]["minutes"] / 60

        dto_list: list[DateHoursDTO] = [
            DateHoursDTO(date=d, hours=h) for d, h in result.items()
        ]

        return dto_list
