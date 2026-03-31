import calendar
from datetime import date, timedelta

from clients.redmine_client import RedmineClient
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
        client = RedmineClient(api_key=self.user.redmine_api_key)
        return client.get_spent_on_dates(
            user_id=self.user.user_id,
            issue_id=self.user.issue_id,
        )
