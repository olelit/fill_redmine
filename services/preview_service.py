from datetime import date

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from dto.preview_dto import DateRangeDTO, PreviewDTO
from services.issue_service import IssueService


class PreviewService:
    @staticmethod
    def get_issue_info(
        issue_info_cache: dict[int, IssueInfoDTO | None],
        project: ProjectConfig,
    ) -> IssueInfoDTO | None:
        config = project.trackers.get("redmine", {})
        issue_id = config.get("issue_id")
        api_key = config.get("api_key", "")
        if not issue_id or not api_key:
            return None

        issue_id = int(issue_id)
        if issue_id not in issue_info_cache:
            issue_info_cache[issue_id] = IssueService.get_issue_info(
                issue_id=issue_id,
                api_key=api_key,
            )
        return issue_info_cache[issue_id]

    @staticmethod
    def build_preview(
        project: ProjectConfig,
        action: str,
        records: list[DateHoursDTO],
        issue_info: IssueInfoDTO | None,
        error: str | None = None,
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

        config = project.trackers.get("redmine", {})
        issue_id = int(config.get("issue_id") or 0)
        return PreviewDTO(
            project_name=project.name,
            action=action,
            issue_id=issue_id,
            comment=config.get("comment", ""),
            issue_subject=issue_info.subject if issue_info else None,
            issue_url=issue_info.url if issue_info else None,
            issue_author=issue_info.author if issue_info else None,
            issue_created_on=issue_info.created_on if issue_info else None,
            ranges=ranges,
            total_hours=total_hours,
            error=error,
        )

    @staticmethod
    def print_header() -> None:
        print("\n" + "=" * 50)
        print("Time entries to be imported")
        print("=" * 50 + "\n")

    @staticmethod
    def print_preview(preview: PreviewDTO) -> None:
        print(f"=== Project: {preview.project_name} ===")
        print(f"Action: {preview.action}")
        if preview.error is not None:
            print(f"Ошибка: {preview.error}")
            print()
            return
        if preview.issue_subject is None:
            print(f"Issue Data: {preview.issue_id}")
        else:
            print(
                f"Issue Data: Id: {preview.issue_id}, "
                f"Author: {preview.issue_author}, Created: {preview.issue_created_on}"
            )
            print(f"Issue: {preview.issue_subject}")
            print(f"Issue URL: {preview.issue_url}")
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
