from configs.user_config import MANUAL, UserConfig
from storage.migration import migrate_from_user_list
from storage.user_repository import UserRepository

USER_LIST_TEMPLATE = '''
from configs.user_config import UserConfig


USERS = [
    UserConfig(
        is_enable=True,
        name="Олег",
        redmine_api_key="key",
        user_id=16,
        activity_id=9,
        comment="development",
        issue_id=2682,
        driver="youtrack",
        youtrack_access_token="token",
        exclude_dates=[],
    ),
]
'''


PARTIAL_FAILURE_TEMPLATE = '''
from configs.user_config import UserConfig


USERS = [
    UserConfig(
        is_enable=True,
        name="Первый",
        redmine_api_key="key",
        user_id=16,
        activity_id=9,
        comment="development",
        issue_id=2682,
        driver="manual",
        youtrack_access_token="",
        exclude_dates=[],
    ),
    UserConfig(
        is_enable=True,
        name="Второй",
        redmine_api_key="key",
        user_id=17,
        activity_id=9,
        comment="development",
        issue_id=2683,
        driver="jira",
        youtrack_access_token="",
        exclude_dates=[],
    ),
]
'''


def existing_user() -> UserConfig:
    return UserConfig(
        is_enable=True,
        name="Existing",
        redmine_api_key="",
        user_id=1,
        activity_id=1,
        comment="",
        issue_id=1,
        driver=MANUAL,
        youtrack_access_token="",
        exclude_dates=[],
    )


class TestMigrateFromUserList:
    def test_migrates_users_and_renames_file(self, tmp_path):
        repo = UserRepository(db_path=tmp_path / "test.db")
        user_list = tmp_path / "user_list.py"
        user_list.write_text(USER_LIST_TEMPLATE)

        result = migrate_from_user_list(repo, user_list_path=user_list, log=lambda message: None)

        assert result is True
        users = repo.list_users()
        assert len(users) == 1
        assert users[0].name == "Олег"
        assert users[0].is_youtrack() is True
        assert not user_list.exists()
        assert (tmp_path / "user_list.py.migrated").exists()

    def test_skips_when_database_not_empty(self, tmp_path):
        repo = UserRepository(db_path=tmp_path / "test.db")
        repo.add_user(existing_user())
        user_list = tmp_path / "user_list.py"
        user_list.write_text(USER_LIST_TEMPLATE)

        result = migrate_from_user_list(repo, user_list_path=user_list, log=lambda message: None)

        assert result is False
        assert len(repo.list_users()) == 1
        assert user_list.exists()

    def test_returns_false_when_file_missing(self, tmp_path):
        repo = UserRepository(db_path=tmp_path / "test.db")

        result = migrate_from_user_list(
            repo, user_list_path=tmp_path / "missing.py", log=lambda message: None
        )

        assert result is False

    def test_partial_failure_rolls_back_and_keeps_file(self, tmp_path):
        repo = UserRepository(db_path=tmp_path / "test.db")
        user_list = tmp_path / "user_list.py"
        user_list.write_text(PARTIAL_FAILURE_TEMPLATE)

        result = migrate_from_user_list(repo, user_list_path=user_list, log=lambda message: None)

        assert result is False
        assert repo.list_users() == []
        assert user_list.exists()

    def test_broken_file_does_not_raise(self, tmp_path):
        repo = UserRepository(db_path=tmp_path / "test.db")
        user_list = tmp_path / "user_list.py"
        user_list.write_text("raise RuntimeError('boom')")

        result = migrate_from_user_list(repo, user_list_path=user_list, log=lambda message: None)

        assert result is False
        assert repo.list_users() == []
        assert user_list.exists()
