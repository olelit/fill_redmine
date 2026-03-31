from unittest.mock import MagicMock, patch

import pytest

from configs.user_config import MANUAL, UserConfig
from dto.date_hours_dto import DateHoursDTO
from fill_redmine import format_created_on, get_issue_info, main


class TestFillRedmine:
    def test_format_created_on_formats_iso_datetime(self):
        result = format_created_on("2026-03-31T08:13:51Z")

        assert result == "2026-03-31 08:13:51 UTC"

    def test_get_issue_info_returns_subject_author_and_url(self):
        with patch("fill_redmine.Config.get_redmine_base_url", return_value="http://redmine/"), \
             patch("fill_redmine.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "issue": {
                    "subject": "Fill Redmine output",
                    "author": {"name": "Oleg"},
                    "created_on": "2026-03-31T08:13:51Z",
                }
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = get_issue_info(issue_id=2574, api_key="test_api_key")

        assert result == {
            "subject": "Fill Redmine output",
            "url": "http://redmine/issues/2574",
            "author": "Oleg",
            "created_on": "2026-03-31 08:13:51 UTC",
        }

    @pytest.mark.asyncio
    async def test_main_prints_issue_details_before_dates(self, capsys):
        user = UserConfig(
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
        )

        mock_importer = MagicMock()
        mock_importer.create_record_list.return_value = [
            DateHoursDTO(date="2026-03-31", hours=8),
        ]
        mock_importer.handle.return_value = None

        with patch("fill_redmine.USERS", [user]), \
             patch("fill_redmine.create_importer", return_value=mock_importer), \
             patch(
                 "fill_redmine.get_issue_info",
                 return_value={
                     "subject": "Issue title",
                     "url": "http://redmine/issues/123",
                     "author": "Oleg",
                     "created_on": "2026-03-30 10:00:00 UTC",
                 },
             ), \
             patch("builtins.input", return_value="n"):
            await main()

        output = capsys.readouterr().out

        assert "Issue ID: 123" in output
        assert "Issue: Issue title" in output
        assert "Issue URL: http://redmine/issues/123" in output
        assert "Issue author: Oleg" in output
        assert "Issue created: 2026-03-30 10:00:00 UTC" in output
        assert output.index("Issue: Issue title") < output.index("Dates:")
