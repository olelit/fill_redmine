from datetime import date
from unittest.mock import MagicMock, patch

from clients.redmine_client import RedmineClient
from trackers.redmine import RedmineTracker


def test_get_time_entries_paginates(monkeypatch):
    monkeypatch.setattr(RedmineClient, "PAGE_SIZE", 2)
    page_one = MagicMock()
    page_one.json.return_value = {
        "time_entries": [
            {"spent_on": "2026-10-01", "hours": 2},
            {"spent_on": "2026-10-02", "hours": 3},
        ],
        "total_count": 3,
    }
    page_one.raise_for_status = MagicMock()
    page_two = MagicMock()
    page_two.json.return_value = {
        "time_entries": [{"spent_on": "2026-10-03", "hours": 4}],
        "total_count": 3,
    }
    page_two.raise_for_status = MagicMock()

    with patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine",
    ), patch(
        "clients.redmine_client.requests.get",
        side_effect=[page_one, page_two],
    ) as mock_get:
        entries = RedmineClient("key").get_time_entries(
            user_id=16, start=date(2026, 10, 1), end=date(2026, 10, 3)
        )

    assert [entry["hours"] for entry in entries] == [2, 3, 4]
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[1].kwargs["params"]["offset"] == 2


def test_tracker_maps_worklogs():
    tracker = RedmineTracker(
        {
            "api_key": "key",
            "user_id": 16,
            "activity_id": 9,
            "issue_id": 2682,
            "comment": "dev",
        }
    )
    with patch.object(
        RedmineClient,
        "get_time_entries",
        return_value=[
            {
                "spent_on": "2026-10-01",
                "hours": 3.5,
                "comments": "fix",
                "issue": {"id": 2682},
            }
        ],
    ):
        worklogs = tracker.get_worklogs(date(2026, 10, 1), date(2026, 10, 2))

    assert len(worklogs) == 1
    assert worklogs[0].hours == 3.5
    assert worklogs[0].description == "fix"
    assert worklogs[0].issue == "2682"
    assert worklogs[0].source == "redmine"


def test_tracker_is_configured():
    assert RedmineTracker({"api_key": "key", "user_id": 1, "activity_id": 2, "issue_id": 3}).is_configured()
    assert not RedmineTracker({}).is_configured()


def test_tracker_is_registered():
    from trackers.registry import get_tracker_class

    assert get_tracker_class("redmine") is RedmineTracker
