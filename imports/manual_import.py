import calendar
from datetime import date, timedelta
import xml.etree.ElementTree as et
import requests

from configs.config import Config
from dto.date_hours_dto import DateHoursDTO
from imports.base_importer import BaseImporter


class ManualImporter(BaseImporter):
    def create_record_list(self) -> list[DateHoursDTO]:
        exclude_dates = self.user.exclude_dates
        start_day = date.today().replace(day=1)
        last_day = calendar.monthrange(start_day.year, start_day.month)[1]
        last_day = start_day.replace(day=last_day)

        spent_on_dates = self.get_times()

        records: list[DateHoursDTO] = []

        while start_day <= last_day:
            day_str = start_day.isoformat()

            if (
                    start_day.weekday() < 5
                    and day_str not in exclude_dates
                    and day_str not in spent_on_dates
            ):
                records.append(DateHoursDTO(date=day_str, hours=8))

            start_day += timedelta(days=1)

        return records

    def get_times(self):
        iid = self.user.issue_id
        uid = self.user.user_id
        api_key = self.user.redmine_api_key
        redmine_url = Config.get_redmine_base_url()

        params = {
            "user_id": uid,
            "issue_id": iid
        }
        headers = {
            "Content-Type": "application/xml",
            "X-Redmine-API-Key": api_key
        }
        url = f"{redmine_url}/time_entries.xml"
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
