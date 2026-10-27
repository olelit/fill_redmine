from configs.project_config import ProjectConfig, ProjectUserConfig
from gui import tracking_view
from gui.tracking_validation import validate_tracking_request
from gui.tracking_view import _trackers_for_users, trackers_for_project
from trackers.base import BaseTracker


def test_valid_request():
    data, errors = validate_tracking_request(
        user_ids=[1],
        destination="redmine",
        source="autofill",
        source_kind="",
        start_text="2026-10-01",
        end_text="2026-10-31",
    )
    assert errors == []
    assert data["destination"] == "redmine"
    assert data["start"].isoformat() == "2026-10-01"


def test_requires_users():
    data, errors = validate_tracking_request(
        [], "redmine", "autofill", "", "2026-10-01", "2026-10-31"
    )
    assert data is None
    assert any("юзера" in error.lower() for error in errors)


def test_tracker_source_cannot_equal_destination():
    data, errors = validate_tracking_request(
        [1], "redmine", "tracker", "redmine", "2026-10-01", "2026-10-31"
    )
    assert data is None
    assert any("совпадать" in error.lower() for error in errors)


def test_bad_period():
    data, errors = validate_tracking_request(
        [1], "redmine", "autofill", "", "2026-10-31", "2026-10-01"
    )
    assert data is None
    assert any("позже" in error.lower() for error in errors)


def test_tracker_source_requires_kind():
    data, errors = validate_tracking_request(
        [1], "redmine", "tracker", "", "2026-10-01", "2026-10-31"
    )
    assert data is None
    assert any("трекер-источник" in error.lower() for error in errors)


def test_bad_date_format():
    data, errors = validate_tracking_request(
        [1], "redmine", "autofill", "", "01.10.2026", "2026-10-31"
    )
    assert data is None
    assert any("формате" in error.lower() for error in errors)


def test_missing_destination():
    data, errors = validate_tracking_request(
        [1], "", "autofill", "", "2026-10-01", "2026-10-31"
    )
    assert data is None
    assert any("назначение" in error.lower() for error in errors)


class _ReadOnlyTracker(BaseTracker):
    kind = "read_only"
    label = "Read only"
    can_read = True
    can_write = False

    def get_worklogs(self, start, end):
        return []


class _WriteOnlyTracker(BaseTracker):
    kind = "write_only"
    label = "Write only"
    can_read = False
    can_write = True

    def get_worklogs(self, start, end):
        return []


class _ReadWriteTracker(BaseTracker):
    kind = "read_write"
    label = "Read write"
    can_read = True
    can_write = True

    def get_worklogs(self, start, end):
        return []


def _users_with_trackers() -> list[ProjectUserConfig]:
    return [
        ProjectUserConfig(
            name="Олег",
            trackers={
                "read_only": {"token": "x"},
                "write_only": {"token": "x"},
                "read_write": {"token": "x"},
                "unconfigured": {},
            },
        )
    ]


def _fake_trackers() -> list[type[BaseTracker]]:
    return [_ReadOnlyTracker, _WriteOnlyTracker, _ReadWriteTracker]


def test_trackers_for_users_source_requires_read(monkeypatch):
    monkeypatch.setattr(tracking_view, "all_trackers", _fake_trackers)
    kinds = [cls.kind for cls in _trackers_for_users(_users_with_trackers())]
    assert kinds == ["read_only", "read_write"]


def test_trackers_for_users_destination_requires_write(monkeypatch):
    monkeypatch.setattr(tracking_view, "all_trackers", _fake_trackers)
    kinds = [
        cls.kind
        for cls in _trackers_for_users(
            _users_with_trackers(), require_read=False, require_write=True
        )
    ]
    assert kinds == ["write_only", "read_write"]


def test_trackers_for_project_is_can_read_view(monkeypatch):
    monkeypatch.setattr(tracking_view, "all_trackers", _fake_trackers)
    project = ProjectConfig(name="Проект", users=_users_with_trackers())
    kinds = [cls.kind for cls in trackers_for_project(project)]
    assert kinds == ["read_only", "read_write"]
