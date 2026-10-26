from datetime import datetime

import requests

from configs.config import Config


class YoutrackClient:
    PAGE_SIZE = 100

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = (Config.get_youtrack_base_url() or "").rstrip("/")

    def get_work_items(self, start_date: datetime, end_date: datetime) -> list[dict]:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.base_url}/api/workItems"
        items: list[dict] = []
        skip = 0

        while True:
            params = {
                "fields": "id,date,duration(minutes),text,issue(idReadable)",
                "start": int(start_date.timestamp() * 1000),
                "end": int(end_date.timestamp() * 1000),
                "$top": self.PAGE_SIZE,
                "$skip": skip,
                "author": "me",
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            batch = response.json()
            items.extend(batch)
            if len(batch) < self.PAGE_SIZE:
                break
            skip += self.PAGE_SIZE

        return items
