import json
from pathlib import Path

from configs.ai_settings import AiSettings
from storage.database import create_schema, get_connection

KEY = "ai_settings"


class SettingsRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = get_connection(db_path)
        create_schema(self.conn)

    def get_ai_settings(self) -> AiSettings:
        row = self.conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (KEY,)
        ).fetchone()
        if row is None:
            return AiSettings()
        try:
            data = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return AiSettings()
        if not isinstance(data, dict):
            return AiSettings()
        keys = data.get("keys")
        if not isinstance(keys, dict):
            keys = {}
        return AiSettings(
            provider=str(data.get("provider") or "opencode_go"),
            model=str(data.get("model") or "deepseek-v4.1-flash"),
            base_url=str(data.get("base_url") or ""),
            keys={str(k): str(v) for k, v in keys.items()},
        )

    def save_ai_settings(self, settings: AiSettings) -> None:
        payload = json.dumps(
            {
                "provider": settings.provider,
                "model": settings.model,
                "base_url": settings.base_url,
                "keys": settings.keys,
            },
            ensure_ascii=False,
        )
        self.conn.execute(
            """INSERT INTO app_settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (KEY, payload),
        )
        self.conn.commit()

    def get_raw(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row is not None else None

    def set_raw(self, key: str, value: str) -> None:
        self.conn.execute(
            """INSERT INTO app_settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        self.conn.commit()
