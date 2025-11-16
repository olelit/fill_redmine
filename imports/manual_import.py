import calendar
import os
from datetime import date, timedelta
import xml.etree.ElementTree as et

import requests

from imports.base_importer import BaseImporter

class ManualImporter(BaseImporter):
    def create_record_list(self):
        exclude_dates = os.getenv(f"EXCLUDE_DATES_{self.postfix}").split(",")
        start_day = date.today().replace(day=1)
        last_day = calendar.monthrange(start_day.year, start_day.month)[1]
        last_day = start_day.replace(day=last_day)
        records = {}
        spent_on_dates = self.get_times()

        while start_day <= last_day:
            day_str = start_day.isoformat()
            if (
                    start_day.weekday() < 5
                    and day_str not in exclude_dates
                    and day_str not in spent_on_dates
            ):
                records[day_str] = 8
            start_day += timedelta(days=1)

        return records

    def get_times(self):

        api_key = os.getenv(f"REDMINE_API_KEY_{self.postfix}")
        uid = os.getenv(f"USER_ID_{self.postfix}")
        iid = os.getenv(f"ISSUE_ID_{self.postfix}")

        params = {
            "user_id": uid,
            "issue_id": iid
        }
        headers = {
            "Content-Type": "application/xml",
            "X-Redmine-API-Key": api_key
        }
        url = f"{self.REDMINE_URL}/time_entries.xml"
        response = requests.get(url, headers=headers, params=params)

        spent_on_dates = set()
        try:
            root = et.fromstring(response.text)
            for entry in root.findall("time_entry"):
                spent_on = entry.find("spent_on")
                if spent_on is not None and spent_on.text:
                    spent_on_dates.add(spent_on.text)
        except Exception as e:
            print(f"XML parse error: {e}")
        return spent_on_dates

