from configs.user_config import MANUAL, YOUTRACK, UserConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from services.preview_service import PreviewService


def make_user(**overrides) -> UserConfig:
    data = dict(
        is_enable=True,
        name="Олег",
        redmine_api_key="key",
        user_id=16,
        activity_id=9,
        comment="development",
        issue_id=2682,
        driver=MANUAL,
        youtrack_access_token="",
        exclude_dates=[],
    )
    data.update(overrides)
    return UserConfig(**data)


def make_issue_info() -> IssueInfoDTO:
    return IssueInfoDTO(
        subject="Тема задачи",
        url="http://redmine/issues/2682",
        author="Oleg",
        created_on="2026-10-01 10:00:00 UTC",
    )


class TestBuildUserPreview:
    def test_groups_consecutive_days_with_equal_hours(self):
        records = [
            DateHoursDTO(date="2026-10-01", hours=8),
            DateHoursDTO(date="2026-10-02", hours=8),
            DateHoursDTO(date="2026-10-05", hours=4),
        ]

        preview = PreviewService.build_user_preview(make_user(), records, make_issue_info())

        assert [(r.start_date, r.end_date, r.hours) for r in preview.ranges] == [
            ("2026-10-01", "2026-10-02", 8),
            ("2026-10-05", "2026-10-05", 4),
        ]
        assert preview.total_hours == 20

    def test_splits_range_when_hours_differ(self):
        records = [
            DateHoursDTO(date="2026-10-01", hours=8),
            DateHoursDTO(date="2026-10-02", hours=4),
        ]

        preview = PreviewService.build_user_preview(make_user(), records, None)

        assert [(r.start_date, r.end_date) for r in preview.ranges] == [
            ("2026-10-01", "2026-10-01"),
            ("2026-10-02", "2026-10-02"),
        ]

    def test_empty_records_produce_empty_preview(self):
        preview = PreviewService.build_user_preview(make_user(), [], None)

        assert preview.ranges == []
        assert preview.total_hours == 0

    def test_copies_user_and_issue_fields(self):
        records = [DateHoursDTO(date="2026-10-01", hours=8)]

        preview = PreviewService.build_user_preview(
            make_user(driver=YOUTRACK, comment="fix"), records, make_issue_info()
        )

        assert preview.user_name == "Олег"
        assert preview.user_id == 16
        assert preview.driver == YOUTRACK
        assert preview.comment == "fix"
        assert preview.issue_id == 2682
        assert preview.issue_subject == "Тема задачи"
        assert preview.issue_url == "http://redmine/issues/2682"
        assert preview.issue_author == "Oleg"
        assert preview.issue_created_on == "2026-10-01 10:00:00 UTC"

    def test_missing_issue_info_keeps_none_fields(self):
        preview = PreviewService.build_user_preview(
            make_user(), [DateHoursDTO(date="2026-10-01", hours=8)], None
        )

        assert preview.issue_subject is None
        assert preview.issue_url is None
