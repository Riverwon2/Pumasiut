from datetime import date

import pytest
from pydantic import ValidationError

from app.agents_workflow import build_planner_input
from app.models import HelpRequest


def test_end_time_must_be_later_than_start_time() -> None:
    with pytest.raises(ValidationError):
        HelpRequest(
            requester_name="김하늘",
            request_text="출근 준비를 도와주세요.",
            date=date(2026, 8, 3),
            start_time="09:00",
            end_time="08:00",
        )


def test_planner_input_marks_ui_schedule_as_authoritative() -> None:
    request = HelpRequest(
        requester_name="김하늘",
        request_text="내일 10시에 출근 준비를 도와주세요.",
        date=date(2026, 8, 5),
        start_time="08:00",
        end_time="09:00",
    )
    planner_input = build_planner_input(request)
    assert "자연어보다 우선하는 확정값" in planner_input
    assert '"date": "2026-08-05"' in planner_input
    assert '"startTime": "08:00"' in planner_input
