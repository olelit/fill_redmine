from datetime import datetime

import requests

from configs.config import Config


class YoutrackClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = (Config.get_youtrack_base_url() or "").rstrip("/")

    def get_work_items(self, start_date: datetime, end_date: datetime) -> list[dict]:
        params = {
            "fields": "date,duration(minutes)",
            "start": int(start_date.timestamp() * 1000),
            "end": int(end_date.timestamp() * 1000),
            "$top": 500,
            "author": "me",
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}

        url = f"{self.base_url}/api/workItems"
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
