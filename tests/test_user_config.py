import pytest

from configs.user_config import UserConfig, MANUAL, YOUTRACK


class TestUserConfig:
    def test_is_manual_returns_true_for_manual_driver(self):
        user = UserConfig(
            is_enable=True,
            name="Test",
            redmine_api_key="key",
            user_id=1,
            activity_id=1,
            comment="test",
            issue_id=1,
            driver=MANUAL,
            youtrack_access_token="",
        )
        assert user.is_manual() is True

    def test_is_manual_returns_false_for_youtrack_driver(self):
        user = UserConfig(
            is_enable=True,
            name="Test",
            redmine_api_key="key",
            user_id=1,
            activity_id=1,
            comment="test",
            issue_id=1,
            driver=YOUTRACK,
            youtrack_access_token="",
        )
        assert user.is_manual() is False

    def test_is_youtrack_returns_true_for_youtrack_driver(self):
        user = UserConfig(
            is_enable=True,
            name="Test",
            redmine_api_key="key",
            user_id=1,
            activity_id=1,
            comment="test",
            issue_id=1,
            driver=YOUTRACK,
            youtrack_access_token="token",
        )
        assert user.is_youtrack() is True

    def test_is_youtrack_returns_false_for_manual_driver(self):
        user = UserConfig(
            is_enable=True,
            name="Test",
            redmine_api_key="key",
            user_id=1,
            activity_id=1,
            comment="test",
            issue_id=1,
            driver=MANUAL,
            youtrack_access_token="",
        )
        assert user.is_youtrack() is False
