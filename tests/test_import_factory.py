import pytest

from configs.project_config import ProjectConfig
from dto.import_action import ImportAction
from imports.import_factory import create_importer
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter


def make_project(**overrides) -> ProjectConfig:
    data = dict(
        name="Проект",
        exclude_dates=[],
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 16,
                "activity_id": 9,
                "issue_id": 2682,
                "comment": "dev",
            },
            "youtrack": {"access_token": "token"},
        },
    )
    data.update(overrides)
    return ProjectConfig(**data)


def test_creates_manual_importer():
    assert isinstance(
        create_importer(make_project(), ImportAction.REDMINE_FILL),
        ManualImporter,
    )


def test_creates_youtrack_importer():
    assert isinstance(
        create_importer(make_project(), ImportAction.YOUTRACK_TRANSFER),
        YoutrackImporter,
    )


def test_unknown_action_raises():
    with pytest.raises(ValueError):
        create_importer(make_project(), "unknown")
