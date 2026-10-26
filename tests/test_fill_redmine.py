from unittest.mock import MagicMock, patch

import pytest

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.import_action import ImportAction
from dto.issue_info_dto import IssueInfoDTO
from fill_redmine import main
from services.issue_service import IssueService


def make_project() -> ProjectConfig:
    return ProjectConfig(
        name="Test Project",
        db_id=1,
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 1,
                "activity_id": 9,
                "issue_id": 123,
                "comment": "test work",
            }
        },
    )


def test_format_created_on_formats_iso_datetime():
    assert (
        IssueService.format_created_on("2026-03-31T08:13:51Z")
        == "2026-03-31 08:13:51 UTC"
    )


def test_get_issue_info_returns_subject_author_and_url():
    with patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine/",
    ), patch("clients.redmine_client.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "issue": {
                "subject": "Issue title",
                "author": {"name": "Oleg"},
                "created_on": "2026-03-31T08:13:51Z",
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = IssueService.get_issue_info(issue_id=2574, api_key="key")

    assert result == IssueInfoDTO(
        subject="Issue title",
        url="http://redmine/issues/2574",
        author="Oleg",
        created_on="2026-03-31 08:13:51 UTC",
    )


@pytest.mark.asyncio
async def test_main_prints_project_preview(capsys):
    mock_importer = MagicMock()
    mock_importer.create_record_list.return_value = [
        DateHoursDTO(date="2026-03-31", hours=8)
    ]
    mock_importer.handle.return_value = []
    mock_repo = MagicMock()
    mock_repo.get_project.return_value = make_project()

    with patch(
        "services.import_service.create_importer",
        return_value=mock_importer,
    ), patch(
        "services.import_service.PreviewService.get_issue_info",
        return_value=IssueInfoDTO(
            subject="Issue title",
            url="http://redmine/issues/123",
            author="Oleg",
            created_on="2026-03-30 10:00:00 UTC",
        ),
    ), patch("builtins.input", return_value="n"):
        await main(
            project_id=1,
            action=ImportAction.REDMINE_FILL,
            repo=mock_repo,
        )

    output = capsys.readouterr().out
    assert "=== Project: Test Project ===" in output
    assert "Issue: Issue title" in output
    assert output.index("Issue: Issue title") < output.index("Dates:")
