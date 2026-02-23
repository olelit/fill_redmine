from unittest.mock import MagicMock, patch

import pytest

from configs.user_config import UserConfig, YOUTRACK
from imports.youtrack_import import YoutrackImporter
from dto.date_hours_dto import DateHoursDTO


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
        
        with patch("imports.youtrack_import.requests.get") as mock_get, \
             patch("imports.youtrack_import.Config.get_youtrack_base_url", return_value="http://youtrack"):
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
        
        with patch("imports.youtrack_import.requests.get") as mock_get, \
             patch("imports.youtrack_import.Config.get_youtrack_base_url", return_value="http://youtrack"):
            mock_response = MagicMock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            records = importer.create_record_list()
            
            assert len(records) == 1
            assert records[0].hours == 8.0

    def test_create_record_list_uses_bearer_token(self, importer):
        mock_data = []
        
        with patch("imports.youtrack_import.requests.get") as mock_get, \
             patch("imports.youtrack_import.Config.get_youtrack_base_url", return_value="http://youtrack"):
            mock_response = MagicMock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            importer.create_record_list()
            
            mock_get.assert_called_once()
            headers = mock_get.call_args[1]["headers"]
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer test_token"
