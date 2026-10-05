from datetime import date

from configs.user_config import UserConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from dto.preview_dto import DateRangeDTO, PreviewDTO
from services.issue_service import IssueService


class PreviewService:
    @staticmethod
    def get_issue_info(
        issue_info_cache: dict[int, IssueInfoDTO | None],
        user: UserConfig,
    ) -> IssueInfoDTO | None:
        if user.issue_id not in issue_info_cache:
            issue_info_cache[user.issue_id] = IssueService.get_issue_info(
                issue_id=user.issue_id,
                api_key=user.redmine_api_key,
            )

        return issue_info_cache[user.issue_id]

    @staticmethod
    def build_user_preview(
        user: UserConfig,
        records: list[DateHoursDTO],
        issue_info: IssueInfoDTO | None,
    ) -> PreviewDTO:
        ranges: list[DateRangeDTO] = []
        total_hours: float = 0

        if records:
            range_start = records[0]
            prev = records[0]
            range_count = 1

            for record in records[1:]:
                prev_dt = date.fromisoformat(prev.date)
                curr_dt = date.fromisoformat(record.date)
                if record.hours == prev.hours and (curr_dt - prev_dt).days == 1:
                    prev = record
                    range_count += 1
                else:
                    ranges.append(
                        DateRangeDTO(range_start.date, prev.date, range_start.hours)
                    )
                    total_hours += range_count * range_start.hours
                    range_start = record
                    prev = record
                    range_count = 1

            ranges.append(DateRangeDTO(range_start.date, prev.date, range_start.hours))
            total_hours += range_count * range_start.hours

        return PreviewDTO(
            user_name=user.name,
            user_id=user.user_id,
            driver=user.driver,
            comment=user.comment,
            issue_id=user.issue_id,
            issue_subject=issue_info.subject if issue_info else None,
            issue_url=issue_info.url if issue_info else None,
            issue_author=issue_info.author if issue_info else None,
            issue_created_on=issue_info.created_on if issue_info else None,
            ranges=ranges,
            total_hours=total_hours,
        )

    @staticmethod
    def print_header() -> None:
        print("\n" + "=" * 50)
        print("Time entries to be imported")
        print("=" * 50 + "\n")

    @staticmethod
    def print_preview(preview: PreviewDTO) -> None:
        print(f"=== User: {preview.user_name} (user_id={preview.user_id}) ===")
        if preview.issue_subject is None:
            print(f"Issue Data: {preview.issue_id}")
        else:
            print(
                f"Issue Data: Id: {preview.issue_id}, "
                f"Author: {preview.issue_author}, Created: {preview.issue_created_on}"
            )
            print(f"Issue: {preview.issue_subject}")
            print(f"Issue URL: {preview.issue_url}")
        print(f"Driver: {preview.driver}")
        print(f"Comment: {preview.comment}")
        print("Dates:")
        for date_range in preview.ranges:
            if date_range.start_date == date_range.end_date:
                print(f"  {date_range.start_date} - {date_range.hours}h")
            else:
                print(
                    f"  {date_range.start_date} - {date_range.end_date} - "
                    f"{date_range.hours}h"
                )
        print(f"Total hours: {preview.total_hours}h")
        print()
