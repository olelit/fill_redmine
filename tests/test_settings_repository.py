from configs.ai_settings import AiSettings
from storage.settings_repository import SettingsRepository


def test_defaults(tmp_path):
    repo = SettingsRepository(db_path=tmp_path / "test.db")

    settings = repo.get_ai_settings()

    assert settings.provider == "opencode_go"
    assert settings.model == "deepseek-v4.1-flash"
    assert settings.keys == {}


def test_roundtrip(tmp_path):
    repo = SettingsRepository(db_path=tmp_path / "test.db")
    settings = AiSettings(
        provider="openai",
        model="gpt-6",
        keys={"openai": "secret"},
    )

    repo.save_ai_settings(settings)

    assert repo.get_ai_settings() == settings
