from datetime import datetime
from unittest.mock import patch

import pytest

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from imports.youtrack_import import YoutrackImporter


@pytest.fixture
def project():
    return ProjectConfig(
        name="Проект",
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 1,
                "activity_id": 9,
                "issue_id": 123,
                "comment": "test",
            },
            "youtrack": {"access_token": "test_token"},
        },
    )


def test_aggregates_hours_by_date(project):
    importer = YoutrackImporter(project)
    with patch(
        "imports.youtrack_import.YoutrackClient.get_work_items",
        return_value=[
            {"date": 1704067200000, "duration": {"minutes": 240}},
            {"date": 1704067200000, "duration": {"minutes": 240}},
        ],
    ):
        records = importer.create_record_list()

    assert len(records) == 1
    assert isinstance(records[0], DateHoursDTO)
    assert records[0].hours == 8.0


def test_uses_bearer_token(project):
    importer = YoutrackImporter(project)
    with patch("imports.youtrack_import.YoutrackClient") as mock_client:
        mock_client.return_value.get_work_items.return_value = []
        importer.create_record_list()

    mock_client.assert_called_once_with(access_token="test_token")


def test_requests_current_month(project):
    importer = YoutrackImporter(project)
    fixed = datetime(2026, 4, 30, 12, 0, 0)
    with patch("imports.youtrack_import.datetime") as mock_datetime, patch(
        "imports.youtrack_import.YoutrackClient.get_work_items",
        return_value=[],
    ) as mock_get:
        mock_datetime.now.return_value = fixed
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp
        importer.create_record_list()

    _, kwargs = mock_get.call_args
    assert kwargs["start_date"] == datetime(2026, 4, 1)
    assert kwargs["end_date"] == datetime(2026, 5, 1)


def test_missing_youtrack_token_raises(project):
    project.trackers.pop("youtrack")
    importer = YoutrackImporter(project)

    with pytest.raises(ValueError, match="YouTrack"):
        importer.create_record_list()
