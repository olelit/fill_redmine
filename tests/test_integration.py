from unittest.mock import patch

import pytest

from configs.project_config import ProjectConfig
from dto.import_action import ImportAction
from imports.import_factory import create_importer
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter


class MockResponse:
    status = 201

    async def text(self):
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockSession:
    def post(self, *args, **kwargs):
        return MockResponse()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def make_project(**overrides) -> ProjectConfig:
    data = dict(
        name="Test",
        trackers={
            "redmine": {
                "api_key": "test_api_key",
                "user_id": 1,
                "activity_id": 9,
                "issue_id": 123,
                "comment": "test work",
            },
            "youtrack": {"access_token": "test_token"},
        },
    )
    data.update(overrides)
    return ProjectConfig(**data)


@pytest.mark.asyncio
async def test_full_manual_import_flow_with_mocks():
    importer = ManualImporter(make_project())

    with patch.object(importer, "get_times", return_value=set()), patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine",
    ), patch(
        "clients.redmine_client.aiohttp.ClientSession",
        return_value=MockSession(),
    ):
        records = importer.create_record_list()
        assert records
        await importer.handle()


@pytest.mark.asyncio
async def test_full_youtrack_import_flow_with_mocks():
    importer = YoutrackImporter(make_project())

    with patch(
        "imports.youtrack_import.YoutrackClient.get_work_items",
        return_value=[{"date": 1704067200000, "duration": {"minutes": 480}}],
    ), patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine",
    ), patch(
        "clients.redmine_client.aiohttp.ClientSession",
        return_value=MockSession(),
    ):
        records = importer.create_record_list()
        assert records
        await importer.handle()


def test_factory_returns_importers():
    assert isinstance(
        create_importer(make_project(), ImportAction.REDMINE_FILL),
        ManualImporter,
    )
    assert isinstance(
        create_importer(make_project(), ImportAction.YOUTRACK_TRANSFER),
        YoutrackImporter,
    )
