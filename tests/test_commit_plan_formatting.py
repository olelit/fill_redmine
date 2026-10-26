from dto.commit_plan_dto import CommitPlanDTO, DayPlanDTO
from gui.commit_plan_view import format_plan_text


def test_format_plan_text_contains_days_and_summary():
    plan = CommitPlanDTO(
        summary="Итог",
        days=[
            DayPlanDTO(
                date="2026-10-01",
                existing_hours=3,
                deficit_hours=5,
                planned_hours=4,
                comment="Импорт",
                commit_hashes=["aaa111"],
                confidence="high",
            )
        ],
    )

    text = format_plan_text(plan)

    assert "Итог" in text
    assert "2026-10-01" in text
    assert "4h" in text
    assert "Импорт" in text


def test_format_plan_text_without_proposals_returns_fallback():
    plan = CommitPlanDTO(summary="Итог", days=[])

    assert format_plan_text(plan) == "Нет предложений по часам."
