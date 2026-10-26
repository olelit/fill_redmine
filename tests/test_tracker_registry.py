from datetime import date

import pytest

from configs.project_config import ProjectConfig
from trackers import registry
from trackers.base import BaseTracker, TrackerField
from trackers.registry import (
    all_trackers,
    build_tracker,
    configured_trackers,
    get_tracker_class,
    register_tracker,
)


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Глобальный реестр изолируется между тестами и восстанавливается после них."""
    saved = dict(registry._REGISTRY)
    registry._REGISTRY.clear()
    yield
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)


class FakeTracker(BaseTracker):
    kind = "fake_test"
    label = "Fake"
    fields = (
        TrackerField("token", "Token", kind="secret"),
        TrackerField("user_id", "User ID", kind="int"),
    )

    def get_worklogs(self, start: date, end: date):
        return []


def test_register_and_build():
    register_tracker(FakeTracker)

    assert get_tracker_class("fake_test") is FakeTracker
    assert FakeTracker in all_trackers()
    tracker = build_tracker("fake_test", {"token": "t", "user_id": 1})
    assert isinstance(tracker, FakeTracker)


def test_duplicate_registration_raises():
    register_tracker(FakeTracker)

    with pytest.raises(ValueError):
        register_tracker(FakeTracker)


def test_is_configured_requires_all_required_fields():
    tracker = FakeTracker({"token": "t"})

    assert tracker.is_configured() is False


def test_empty_config_is_not_configured():
    assert FakeTracker({}).is_configured() is False


def test_validate_config_allows_empty_section():
    assert FakeTracker.validate_config({}) == []


def test_validate_config_reports_partial_fields():
    errors = FakeTracker.validate_config({"token": "t"})

    assert len(errors) == 1
    assert "Fake" in errors[0]
    assert "User ID" in errors[0]


def test_validate_config_reports_bad_int():
    errors = FakeTracker.validate_config({"token": "t", "user_id": "abc"})

    assert any("User ID" in error for error in errors)


def test_configured_trackers_filters_unconfigured():
    register_tracker(FakeTracker)
    project = ProjectConfig(
        name="P",
        trackers={"fake_test": {"token": "t", "user_id": 1}},
    )

    trackers = configured_trackers(project)

    assert [type(tracker) for tracker in trackers] == [FakeTracker]
