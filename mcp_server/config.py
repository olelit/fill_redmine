import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class UserProfile:
    name: str
    is_enable: bool
    git_email: str = ""
    redmine: dict[str, object] = field(default_factory=dict, repr=False)
    youtrack: dict[str, object] = field(default_factory=dict, repr=False)


class ProfileConfigError(Exception):
    """Raised when the user profile configuration is unusable.

    Messages never contain file contents or credentials.
    """


def default_users_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "users.json"


def load_users(path: Path | None = None) -> list[UserProfile]:
    config_path = Path(path) if path is not None else default_users_path()

    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ProfileConfigError(f"Users config file not found: {config_path}") from None
    except UnicodeDecodeError:
        raise ProfileConfigError(f"Users config file is not valid UTF-8: {config_path}") from None
    except OSError:
        raise ProfileConfigError(f"Cannot read users config file: {config_path}") from None

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        raise ProfileConfigError(f"Users config file is not valid JSON: {config_path}") from None

    if not isinstance(raw, dict):
        raise ProfileConfigError("Users config root must be a JSON object")

    items = raw.get("users")
    if not isinstance(items, list):
        raise ProfileConfigError("Users config must contain a 'users' array")

    return [_parse_profile(item, index) for index, item in enumerate(items)]


def _parse_profile(item: object, index: int) -> UserProfile:
    label = f"users[{index}]"
    if not isinstance(item, dict):
        raise ProfileConfigError(f"{label} must be a JSON object")

    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ProfileConfigError(f"{label}.name must be a non-blank string")

    is_enable = item.get("is_enable")
    if not isinstance(is_enable, bool):
        raise ProfileConfigError(f"{label}.is_enable must be a boolean")

    git_email = item.get("git_email", "")
    if not isinstance(git_email, str):
        raise ProfileConfigError(f"{label}.git_email must be a string")

    redmine = item.get("redmine", {})
    if not isinstance(redmine, dict):
        raise ProfileConfigError(f"{label}.redmine must be a JSON object")

    youtrack = item.get("youtrack", {})
    if not isinstance(youtrack, dict):
        raise ProfileConfigError(f"{label}.youtrack must be a JSON object")

    return UserProfile(
        name=name,
        is_enable=is_enable,
        git_email=git_email,
        redmine=dict(redmine),
        youtrack=dict(youtrack),
    )


def select_user(users: list[UserProfile], name: str | None = None) -> UserProfile:
    enabled = [user for user in users if user.is_enable]

    if name is not None:
        matches = [user for user in enabled if user.name == name]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ProfileConfigError(f"No enabled user profile named {name!r}")
        raise ProfileConfigError(f"Multiple enabled user profiles named {name!r}")

    if not enabled:
        raise ProfileConfigError("No enabled user profiles are configured")
    if len(enabled) > 1:
        raise ProfileConfigError(
            "Multiple enabled user profiles are configured; specify a profile name"
        )
    return enabled[0]
