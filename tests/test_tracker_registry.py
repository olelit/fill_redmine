from datetime import date

import pytest

from trackers import registry
from trackers.base import BaseTracker
from trackers.registry import get_tracker_class, register_tracker


@pytest.fixture(autouse=True)
def _isolated_registry():
    saved = dict(registry._REGISTRY)
    registry._REGISTRY.clear()
    yield
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)


class FakeTracker(BaseTracker):
    kind = "fake_test"
    label = "Fake"

    def get_worklogs(self, start: date, end: date):
        return []


def test_register_and_get():
    register_tracker(FakeTracker)

    assert get_tracker_class("fake_test") is FakeTracker


def test_duplicate_registration_raises():
    register_tracker(FakeTracker)

    with pytest.raises(ValueError):
        register_tracker(FakeTracker)