import os
from datetime import datetime, timedelta

import requests

from imports.base_importer import BaseImporter


class YoutrackImporter(BaseImporter):
    YOUTRACK_BASE_URL = os.getenv("YOUTRACK_BASE_URL")

    def create_record_list(self):
        youtrack_url = os.getenv("YOUTRACK_BASE_URL")
        youtrack_token = os.getenv(f"YOUTRACK_ACCESS_TOKEN_{self.postfix}")
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

        x = os.environ

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
        return result
