from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.import_action import ImportAction
from work_assistant_cli import main


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
                "comment": "test",
            }
        },
    )


@pytest.mark.asyncio
async def test_main_lists_projects_when_no_id(capsys):
    repo = MagicMock()
    repo.list_projects.return_value = [make_project()]

    await main(repo=repo)

    output = capsys.readouterr().out
    assert "1: Test Project" in output


@pytest.mark.asyncio
async def test_main_runs_import_for_project(capsys):
    importer = MagicMock()
    importer.create_record_list.return_value = [
        DateHoursDTO(date="2026-10-01", hours=8)
    ]
    importer.handle = AsyncMock(return_value=[])
    repo = MagicMock()
    repo.get_project.return_value = make_project()

    with patch(
        "services.import_service.create_importer", return_value=importer
    ), patch(
        "services.import_service.PreviewService.get_issue_info",
        return_value=None,
    ), patch("builtins.input", return_value="y"):
        await main(
            project_id=1,
            action=ImportAction.REDMINE_FILL,
            repo=repo,
        )

    output = capsys.readouterr().out
    assert "=== Project: Test Project ===" in output
    assert "Import finished" in output
