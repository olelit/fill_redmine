from configs.user_config import UserConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
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
    def print_header() -> None:
        print("\n" + "=" * 50)
        print("Time entries to be imported")
        print("=" * 50 + "\n")

    @staticmethod
    def print_user_preview(
        user: UserConfig,
        records: list[DateHoursDTO],
        issue_info: IssueInfoDTO | None,
    ) -> None:
        print(f"=== User: {user.name} (user_id={user.user_id}) ===")
        print(f"Issue ID: {user.issue_id}")
        PreviewService.print_issue_info(issue_info)
        print(f"Driver: {user.driver}")
        print(f"Comment: {user.comment}")
        print("Dates:")

        total_hours = 0
        for record in records:
            print(f"  {record.date} - {record.hours}h")
            total_hours += record.hours

        print(f"Total hours: {total_hours}h")
        print()

    @staticmethod
    def print_issue_info(issue_info: IssueInfoDTO | None) -> None:
        if not issue_info:
            return

        print(f"Issue: {issue_info.subject}")
        print(f"Issue URL: {issue_info.url}")
        print(f"Issue author: {issue_info.author}")
        print(f"Issue created: {issue_info.created_on}")
