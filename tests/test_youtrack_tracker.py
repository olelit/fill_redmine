from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from clients.youtrack_client import YoutrackClient
from dto.worklog_dto import WorklogDTO
from trackers.youtrack import YoutrackTracker


def test_get_work_items_paginates(monkeypatch):
    monkeypatch.setattr(YoutrackClient, "PAGE_SIZE", 2)
    page_one = MagicMock()
    page_one.json.return_value = [{"date": 1}, {"date": 2}]
    page_one.raise_for_status = MagicMock()
    page_two = MagicMock()
    page_two.json.return_value = [{"date": 3}]
    page_two.raise_for_status = MagicMock()

    with patch(
        "clients.youtrack_client.Config.get_youtrack_base_url",
        return_value="http://youtrack",
    ), patch(
        "clients.youtrack_client.requests.get",
        side_effect=[page_one, page_two],
    ) as mock_get:
        items = YoutrackClient("token").get_work_items(
            datetime(2026, 10, 1), datetime(2026, 10, 31)
        )

    assert len(items) == 3
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[1].kwargs["params"]["$skip"] == 2


def test_tracker_aggregates_minutes_by_day():
    tracker = YoutrackTracker({"access_token": "token"})
    with patch.object(
        YoutrackClient,
        "get_work_items",
        return_value=[
            {"date": 1790812800000, "duration": {"minutes": 120}, "text": "a"},
            {"date": 1790812800000, "duration": {"minutes": 240}, "text": "b"},
            {"date": 1790899200000, "duration": {"minutes": 480}, "text": "c"},
        ],
    ):
        worklogs = tracker.get_worklogs(date(2026, 10, 1), date(2026, 10, 2))

    assert [(w.date, w.hours) for w in worklogs] == [
        ("2026-10-01", 6.0),
        ("2026-10-02", 8.0),
    ]
    assert worklogs[0].source == "youtrack"


def test_tracker_is_configured():
    assert YoutrackTracker(
        {"access_token": "token", "issue_id": "PROJ-1"}
    ).is_configured()
    assert not YoutrackTracker({}).is_configured()


def test_tracker_is_registered():
    from trackers.registry import get_tracker_class

    assert get_tracker_class("youtrack") is YoutrackTracker


def test_create_worklogs_posts_work_items():
    tracker = YoutrackTracker({"access_token": "token", "issue_id": "PROJ-1"})
    response = MagicMock()
    response.status_code = 200
    response.text = "{}"

    with patch(
        "clients.youtrack_client.Config.get_youtrack_base_url",
        return_value="http://youtrack",
    ), patch(
        "clients.youtrack_client.requests.post",
        return_value=response,
    ) as mock_post:
        errors = tracker.create_worklogs(
            [WorklogDTO(date="2026-10-27", hours=4, description="dev")]
        )

    assert errors == []
    body = mock_post.call_args.kwargs["json"]
    assert body["duration"]["minutes"] == 240
    assert body["text"] == "dev"
    assert "PROJ-1" in mock_post.call_args.args[0]


def test_create_worklogs_requires_issue_id():
    tracker = YoutrackTracker({"access_token": "token"})

    with pytest.raises(ValueError, match="issue_id"):
        tracker.create_worklogs(
            [WorklogDTO(date="2026-10-27", hours=4, description="dev")]
        )
