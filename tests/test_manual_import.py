from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from configs.user_config import UserConfig, MANUAL
from imports.manual_import import ManualImporter
from dto.date_hours_dto import DateHoursDTO


class TestManualImporter:
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
            driver=MANUAL,
            youtrack_access_token="",
            exclude_dates=["2026-02-15"],
        )

    @pytest.fixture
    def importer(self, user):
        return ManualImporter(user)

    def test_create_record_list_returns_list_of_date_hours_dto(self, importer):
        with patch.object(importer, "get_times", return_value=set()):
            records = importer.create_record_list()
            assert isinstance(records, list)
            if records:
                assert isinstance(records[0], DateHoursDTO)

    def test_create_record_list_excludes_weekends(self, importer):
        with patch.object(importer, "get_times", return_value=set()):
            records = importer.create_record_list()
            for record in records:
                d = date.fromisoformat(record.date)
                assert d.weekday() < 5

    def test_create_record_list_excludes_exclude_dates(self, importer):
        with patch.object(importer, "get_times", return_value=set()):
            records = importer.create_record_list()
            dates = [r.date for r in records]
            assert "2026-02-15" not in dates

    def test_create_record_list_excludes_already_spent_dates(self, importer):
        with patch.object(importer, "get_times", return_value={"2026-02-01"}):
            records = importer.create_record_list()
            dates = [r.date for r in records]
            assert "2026-02-01" not in dates

    def test_get_times_parses_xml_response(self, importer):
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
        <time_entries type="array">
            <time_entry>
                <spent_on>2026-02-01</spent_on>
            </time_entry>
            <time_entry>
                <spent_on>2026-02-02</spent_on>
            </time_entry>
        </time_entries>"""
        
        with patch("imports.manual_import.requests.get") as mock_get, \
             patch("imports.manual_import.Config.get_redmine_base_url", return_value="http://redmine"):
            mock_response = MagicMock()
            mock_response.text = xml_response
            mock_get.return_value = mock_response
            
            result = importer.get_times()
            
            assert "2026-02-01" in result
            assert "2026-02-02" in result
