from unittest.mock import MagicMock, patch

import pytest

from configs.user_config import UserConfig, MANUAL, YOUTRACK
from imports.import_factory import create_importer
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter


class MockResponse:
    def __init__(self):
        self.status = 201

    async def text(self):
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockSession:
    def __init__(self):
        pass

    def post(self, *args, **kwargs):
        return MockResponse()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class TestIntegration:
    @pytest.fixture
    def users(self):
        return [
            UserConfig(
                is_enable=True,
                name="Test User",
                redmine_api_key="test_api_key",
                user_id=1,
                activity_id=9,
                comment="test work",
                issue_id=123,
                driver=MANUAL,
                youtrack_access_token="",
                exclude_dates=[],
            ),
        ]

    @pytest.mark.asyncio
    async def test_full_manual_import_flow_with_mocks(self, users):
        user = users[0]
        importer = ManualImporter(user)

        mock_session_instance = MockSession()

        with patch.object(importer, "get_times", return_value=set()), \
             patch("clients.redmine_client.Config.get_redmine_base_url", return_value="http://redmine"), \
             patch("clients.redmine_client.aiohttp.ClientSession", return_value=mock_session_instance):

            records = importer.create_record_list()

            assert isinstance(records, list)
            assert len(records) > 0

            await importer.handle()

    @pytest.mark.asyncio
    async def test_full_youtrack_import_flow_with_mocks(self):
        user = UserConfig(
            is_enable=True,
            name="Test User",
            redmine_api_key="test_api_key",
            user_id=1,
            activity_id=9,
            comment="test work",
            issue_id=123,
            driver=YOUTRACK,
            youtrack_access_token="test_token",
            exclude_dates=[],
        )
        importer = YoutrackImporter(user)

        mock_data = [
            {"date": 1704067200000, "duration": {"minutes": 480}},
        ]

        mock_session_instance = MockSession()

        with patch("clients.youtrack_client.requests.get") as mock_get, \
             patch("clients.youtrack_client.Config.get_youtrack_base_url", return_value="http://youtrack"), \
             patch("clients.redmine_client.Config.get_redmine_base_url", return_value="http://redmine"), \
             patch("clients.redmine_client.aiohttp.ClientSession", return_value=mock_session_instance):

            mock_yt_response = MagicMock()
            mock_yt_response.json.return_value = mock_data
            mock_yt_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_yt_response

            records = importer.create_record_list()

            assert isinstance(records, list)
            assert len(records) > 0

            await importer.handle()

    def test_create_importer_for_each_user_type(self):
        manual_user = UserConfig(
            is_enable=True,
            name="Manual",
            redmine_api_key="key",
            user_id=1,
            activity_id=1,
            comment="test",
            issue_id=1,
            driver=MANUAL,
            youtrack_access_token="",
        )

        youtrack_user = UserConfig(
            is_enable=True,
            name="Youtrack",
            redmine_api_key="key",
            user_id=1,
            activity_id=1,
            comment="test",
            issue_id=1,
            driver=YOUTRACK,
            youtrack_access_token="token",
        )

        manual_importer = create_importer(manual_user)
        youtrack_importer = create_importer(youtrack_user)

        assert isinstance(manual_importer, ManualImporter)
        assert isinstance(youtrack_importer, YoutrackImporter)
