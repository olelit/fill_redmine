from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from services.preview_service import PreviewService


def make_project(**overrides) -> ProjectConfig:
    data = dict(
        name="Олег",
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 16,
                "activity_id": 9,
                "issue_id": 2682,
                "comment": "development",
            }
        },
    )
    data.update(overrides)
    return ProjectConfig(**data)


def make_issue_info() -> IssueInfoDTO:
    return IssueInfoDTO(
        subject="Тема задачи",
        url="http://redmine/issues/2682",
        author="Oleg",
        created_on="2026-10-01 10:00:00 UTC",
    )


def test_groups_consecutive_days_with_equal_hours():
    records = [
        DateHoursDTO(date="2026-10-01", hours=8),
        DateHoursDTO(date="2026-10-02", hours=8),
        DateHoursDTO(date="2026-10-05", hours=4),
    ]

    preview = PreviewService.build_preview(
        make_project(), "redmine_fill", records, make_issue_info()
    )

    assert [(r.start_date, r.end_date, r.hours) for r in preview.ranges] == [
        ("2026-10-01", "2026-10-02", 8),
        ("2026-10-05", "2026-10-05", 4),
    ]
    assert preview.total_hours == 20


def test_copies_project_fields():
    preview = PreviewService.build_preview(
        make_project(),
        "youtrack_transfer",
        [DateHoursDTO(date="2026-10-01", hours=8)],
        make_issue_info(),
    )

    assert preview.project_name == "Олег"
    assert preview.action == "youtrack_transfer"
    assert preview.issue_id == 2682
    assert preview.comment == "development"
    assert preview.issue_subject == "Тема задачи"
    assert preview.issue_url == "http://redmine/issues/2682"


def test_error_is_stored():
    preview = PreviewService.build_preview(
        make_project(), "redmine_fill", [], None, error="сбой сети"
    )

    assert preview.error == "сбой сети"
    assert preview.ranges == []
    assert preview.total_hours == 0


def test_print_preview_uses_project_name(capsys):
    preview = PreviewService.build_preview(
        make_project(), "redmine_fill", [], None, error="сбой сети"
    )

    PreviewService.print_preview(preview)

    output = capsys.readouterr().out
    assert "=== Project: Олег ===" in output
    assert "Ошибка: сбой сети" in output
