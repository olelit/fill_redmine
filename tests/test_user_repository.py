import pytest

from configs.user_config import UserConfig
from storage.user_repository import UserRepository


def make_user(**overrides) -> UserConfig:
    data = dict(
        is_enable=True,
        name="Олег",
        redmine_api_key="key",
        user_id=16,
        activity_id=9,
        comment="development",
        issue_id=2682,
        driver="youtrack",
        youtrack_access_token="token",
        exclude_dates=["2026-10-01"],
    )
    data.update(overrides)
    return UserConfig(**data)


@pytest.fixture
def repo(tmp_path):
    return UserRepository(db_path=tmp_path / "test.db")


class TestUserRepository:
    def test_list_users_returns_empty_for_new_db(self, repo):
        assert repo.list_users() == []

    def test_add_and_list_users_roundtrip(self, repo):
        db_id = repo.add_user(make_user())

        users = repo.list_users()

        assert len(users) == 1
        assert db_id == 1
        assert users[0].name == "Олег"
        assert users[0].is_enable is True
        assert users[0].driver == "youtrack"
        assert users[0].exclude_dates == ["2026-10-01"]
        assert users[0].is_youtrack() is True

    def test_get_user_returns_none_for_missing(self, repo):
        assert repo.get_user(999) is None

    def test_update_user_changes_fields(self, repo):
        db_id = repo.add_user(make_user())

        repo.update_user(db_id, make_user(name="Новое имя", is_enable=False))

        user = repo.get_user(db_id)
        assert user.name == "Новое имя"
        assert user.is_enable is False

    def test_update_user_for_missing_id_raises(self, repo):
        with pytest.raises(ValueError):
            repo.update_user(999, make_user())

    def test_delete_user(self, repo):
        db_id = repo.add_user(make_user())

        repo.delete_user(db_id)

        assert repo.list_users() == []

    def test_set_enabled_toggles_flag(self, repo):
        db_id = repo.add_user(make_user())

        repo.set_enabled(db_id, False)
        assert repo.get_user(db_id).is_enable is False

        repo.set_enabled(db_id, True)
        assert repo.get_user(db_id).is_enable is True

    def test_add_users_inserts_multiple_users(self, repo):
        repo.add_users([make_user(name="Первый"), make_user(name="Второй")])

        users = repo.list_users()
        assert len(users) == 2
        assert [user.name for user in users] == ["Первый", "Второй"]

    def test_list_users_populates_db_id(self, repo):
        db_id = repo.add_user(make_user())

        users = repo.list_users()

        assert users[0].db_id == db_id
