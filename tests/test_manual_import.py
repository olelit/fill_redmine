from datetime import date
from unittest.mock import patch

import pytest

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from imports.manual_import import ManualImporter


@pytest.fixture
def project():
    return ProjectConfig(
        name="Проект",
        exclude_dates=["2026-02-15"],
        trackers={
            "redmine": {
                "api_key": "test_api_key",
                "user_id": 1,
                "activity_id": 9,
                "issue_id": 123,
                "comment": "test",
            }
        },
    )


@pytest.fixture
def importer(project):
    return ManualImporter(project)


def test_create_record_list_returns_date_hours_dto(importer):
    with patch.object(importer, "get_times", return_value=set()):
        records = importer.create_record_list()

    assert isinstance(records, list)
    assert all(isinstance(record, DateHoursDTO) for record in records)


def test_create_record_list_excludes_weekends(importer):
    with patch.object(importer, "get_times", return_value=set()):
        records = importer.create_record_list()

    assert all(date.fromisoformat(record.date).weekday() < 5 for record in records)


def test_create_record_list_excludes_exclude_dates(importer):
    with patch.object(importer, "get_times", return_value=set()):
        records = importer.create_record_list()

    assert "2026-02-15" not in [record.date for record in records]


def test_create_record_list_excludes_already_spent_dates(importer):
    with patch.object(importer, "get_times", return_value={"2026-02-02"}):
        records = importer.create_record_list()

    assert "2026-02-02" not in [record.date for record in records]


def test_get_times_uses_redmine_config(importer):
    with patch(
        "imports.manual_import.RedmineClient.get_spent_on_dates",
        return_value={"2026-02-01"},
    ) as mock_get:
        result = importer.get_times()

    assert result == {"2026-02-01"}
    mock_get.assert_called_once_with(user_id=1, issue_id=123)


def test_missing_redmine_config_raises(project):
    project.trackers = {}
    importer = ManualImporter(project)

    with pytest.raises(ValueError, match="Redmine"):
        importer.create_record_list()
