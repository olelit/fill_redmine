from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from configs.user_config import YOUTRACK, UserConfig
from dto.date_hours_dto import DateHoursDTO
from imports.youtrack_import import YoutrackImporter


class TestYoutrackImporter:
    @pytest.fixture
    def user(self):
        return UserConfig(
            is_enable=True,
            name="Test",
            redmine_api_key="test_api_key",
            user_id=1,
            activity_id=9,
            comment="test",
            issue_id=123,
            driver=YOUTRACK,
            youtrack_access_token="test_token",
            exclude_dates=[],
        )

    @pytest.fixture
    def importer(self, user):
        return YoutrackImporter(user)

    def test_create_record_list_returns_list_of_date_hours_dto(self, importer):
        mock_data = [
            {"date": 1704067200000, "duration": {"minutes": 480}},
            {"date": 1704153600000, "duration": {"minutes": 480}},
        ]

        with (
            patch("clients.youtrack_client.requests.get") as mock_get,
            patch(
                "clients.youtrack_client.Config.get_youtrack_base_url",
                return_value="http://youtrack",
            ),
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            records = importer.create_record_list()

            assert isinstance(records, list)
            assert isinstance(records[0], DateHoursDTO)

    def test_create_record_list_aggregates_hours_by_date(self, importer):
        mock_data = [
            {"date": 1704067200000, "duration": {"minutes": 240}},
            {"date": 1704067200000, "duration": {"minutes": 240}},
        ]

        with (
            patch("clients.youtrack_client.requests.get") as mock_get,
            patch(
                "clients.youtrack_client.Config.get_youtrack_base_url",
                return_value="http://youtrack",
            ),
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            records = importer.create_record_list()

            assert len(records) == 1
            assert records[0].hours == 8.0

    def test_create_record_list_uses_bearer_token(self, importer):
        mock_data = []

        with (
            patch("clients.youtrack_client.requests.get") as mock_get,
            patch(
                "clients.youtrack_client.Config.get_youtrack_base_url",
                return_value="http://youtrack",
            ),
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            importer.create_record_list()

            mock_get.assert_called_once()
            headers = mock_get.call_args[1]["headers"]
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer test_token"

    def test_create_record_list_sorts_dates_ascending(self, importer):
        mock_data = [
            {"date": 1712016000000, "duration": {"minutes": 480}},
            {"date": 1711929600000, "duration": {"minutes": 480}},
            {"date": 1712102400000, "duration": {"minutes": 480}},
        ]

        with (
            patch("clients.youtrack_client.requests.get") as mock_get,
            patch(
                "clients.youtrack_client.Config.get_youtrack_base_url",
                return_value="http://youtrack",
            ),
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            records = importer.create_record_list()

            assert [record.date for record in records] == [
                "2024-04-01",
                "2024-04-02",
                "2024-04-03",
            ]

    def test_create_record_list_requests_until_next_month_start(self, importer):
        mock_data = []
        fixed_now = datetime(2026, 4, 30, 12, 0, 0)

        with (
            patch("imports.youtrack_import.datetime") as mock_datetime,
            patch("clients.youtrack_client.requests.get") as mock_get,
            patch(
                "clients.youtrack_client.Config.get_youtrack_base_url",
                return_value="http://youtrack",
            ),
        ):
            mock_datetime.now.return_value = fixed_now
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(
                *args, **kwargs
            )
            mock_datetime.fromtimestamp.side_effect = lambda *args, **kwargs: (
                datetime.fromtimestamp(*args, **kwargs)
            )

            mock_response = MagicMock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            importer.create_record_list()

            params = mock_get.call_args[1]["params"]
            assert params["start"] == int(datetime(2026, 4, 1).timestamp() * 1000)
            assert params["end"] == int(datetime(2026, 5, 1).timestamp() * 1000)
