from datetime import date

import pytest
from pydantic import ValidationError

from app.agents_workflow import build_planner_input, create_workflow_agents
from app.models import HelpRequest, SafetyFinding


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
    planner_input = build_planner_input(
        request,
        (
            SafetyFinding(
                finding_id="finding-1",
                source_text="출근 준비를 도와주세요.",
                classification="low",
                category="daily_living",
                reason="일상 생활지원 요청이에요.",
            ),
        ),
    )
    assert "자연어보다 우선하는 확정값" in planner_input
    assert '"date": "2026-08-05"' in planner_input
    assert '"startTime": "08:00"' in planner_input


def test_coordinator_uses_a_blocking_input_guardrail() -> None:
    coordinator = create_workflow_agents()
    assert len(coordinator.input_guardrails) == 1
    assert coordinator.input_guardrails[0].run_in_parallel is False


def test_planner_input_excludes_unapproved_high_risk_text() -> None:
    request = HelpRequest(
        requester_name="김하늘",
        request_text="길 안내가 필요해요. 약을 먹여주세요.",
        date=date(2026, 8, 5),
        start_time="08:00",
        end_time="09:00",
    )
    planner_input = build_planner_input(
        request,
        (
            SafetyFinding(
                finding_id="finding-1",
                source_text="길 안내가 필요해요.",
                classification="low",
                category="daily_living",
                reason="이동 생활지원 요청이에요.",
            ),
        ),
    )
    assert "길 안내가 필요해요" in planner_input
    assert "약을 먹여주세요" not in planner_input
