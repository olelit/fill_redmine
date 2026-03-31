from datetime import datetime

from clients.redmine_client import RedmineClient
from dto.issue_info_dto import IssueInfoDTO


class IssueService:
    @staticmethod
    def get_issue_info(issue_id: int, api_key: str) -> IssueInfoDTO | None:
        client = RedmineClient(api_key=api_key)
        issue = client.get_issue(issue_id=issue_id)
        if not issue:
            return None

        author = issue.get("author") or {}
        return IssueInfoDTO(
            subject=issue.get("subject", "unknown"),
            url=f"{client.base_url}/issues/{issue_id}",
            author=author.get("name", "unknown"),
            created_on=IssueService.format_created_on(issue.get("created_on")),
        )

    @staticmethod
    def format_created_on(created_on: str | None) -> str:
        if not created_on:
            return "unknown"

        try:
            created_at = datetime.fromisoformat(created_on.replace("Z", "+00:00"))
        except ValueError:
            return created_on

        return created_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
