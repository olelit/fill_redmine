from mcp_server.config import ProfileConfigError, UserProfile
from trackers import BaseTracker, get_tracker_class


def build_user_tracker(
    profile: UserProfile,
    kind: str,
    *,
    issue_id: int | None = None,
    for_write: bool = False,
) -> BaseTracker:
    if kind not in ("redmine", "youtrack"):
        raise ProfileConfigError("Unsupported tracker kind")
    tracker_class = get_tracker_class(kind)
    if tracker_class is None:
        raise ProfileConfigError("Unsupported tracker kind")

    config = dict(getattr(profile, kind))
    required = {
        "redmine": ["api_key", "user_id", "activity_id"],
        "youtrack": ["access_token", "issue_id"],
    }[kind]
    if for_write and kind == "redmine":
        if type(issue_id) is not int or issue_id <= 0:
            raise ProfileConfigError("Redmine write requires a valid issue ID")
        config["issue_id"] = issue_id

    credentials = ("api_key",) if kind == "redmine" else ("access_token",)
    missing = [
        key
        for key in required
        if config.get(key) is None
        or config.get(key) == ""
        or isinstance(config.get(key), str) and not config[key].strip()
        or key in credentials and not isinstance(config.get(key), str)
    ]
    if missing:
        raise ProfileConfigError(
            f"{tracker_class.label} configuration is incomplete: {', '.join(missing)}"
        )

    for key in ("user_id", "activity_id") if kind == "redmine" else ():
        raw_value = config[key]
        if type(raw_value) is not int and not isinstance(raw_value, str):
            raise ProfileConfigError(
                f"{tracker_class.label} configuration is invalid: {key}"
            )
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise ProfileConfigError(
                f"{tracker_class.label} configuration is invalid: {key}"
            ) from None
        if value <= 0:
            raise ProfileConfigError(
                f"{tracker_class.label} configuration is invalid: {key}"
            )

    if issue_id is not None and kind == "redmine":
        config["issue_id"] = issue_id
    return tracker_class(config)


def required_redmine_comment(profile: UserProfile) -> str:
    comment = profile.redmine.get("comment")
    if not isinstance(comment, str) or not comment.strip():
        raise ProfileConfigError("Redmine comment is required")
    return comment.strip()
