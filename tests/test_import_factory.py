import pytest

from configs.user_config import UserConfig, MANUAL, YOUTRACK
from imports.import_factory import create_importer
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter


class TestImportFactory:
    def test_create_importer_returns_manual_importer_for_manual_driver(self):
        user = UserConfig(
            is_enable=True,
            name="Test",
            redmine_api_key="key",
            user_id=1,
            activity_id=1,
            comment="test",
            issue_id=1,
            driver=MANUAL,
            youtrack_access_token="",
        )
        importer = create_importer(user)
        assert isinstance(importer, ManualImporter)

    def test_create_importer_returns_youtrack_importer_for_youtrack_driver(self):
        user = UserConfig(
            is_enable=True,
            name="Test",
            redmine_api_key="key",
            user_id=1,
            activity_id=1,
            comment="test",
            issue_id=1,
            driver=YOUTRACK,
            youtrack_access_token="token",
        )
        importer = create_importer(user)
        assert isinstance(importer, YoutrackImporter)

    def test_create_importer_returns_none_for_unknown_driver(self):
        user = UserConfig(
            is_enable=True,
            name="Test",
            redmine_api_key="key",
            user_id=1,
            activity_id=1,
            comment="test",
            issue_id=1,
            driver="unknown",
            youtrack_access_token="",
        )
        importer = create_importer(user)
        assert importer is None
