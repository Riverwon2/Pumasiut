from datetime import date

from app.models import ConfirmTaskMatchRequest, HelpRequest, PlannedTask
from app.scheduling import (
    apply_task_schedule_policy,
    extract_explicit_times,
    uncovered_explicit_times,
)


def request() -> HelpRequest:
    return HelpRequest(
        requester_name="김하늘",
        request_text="병원 예약은 9시 30분이고 10시까지 출근해야 합니다.",
        date=date(2026, 8, 3),
        start_time="08:00",
        end_time="11:00",
    )


def task(**updates: object) -> PlannedTask:
    values: dict[str, object] = {
        "task_id": "task-1",
        "safety_finding_id": "finding-1",
        "title": "병원 이동",
        "description": "보행 보조견을 병원으로 이동합니다.",
        "date": date(2026, 8, 3),
        "start_time": "08:00",
        "end_time": "11:00",
        "risk_level": "low",
    }
    values.update(updates)
    return PlannedTask.model_validate(values)


def test_extracts_korean_appointment_and_deadline_times() -> None:
    assert extract_explicit_times(request().request_text) == ("09:30", "10:00")


def test_ui_time_is_used_only_when_natural_language_time_is_absent() -> None:
    scheduled = apply_task_schedule_policy(task(), request())
    assert scheduled.schedule_source == "ui_default"
    assert (scheduled.start_time, scheduled.end_time) == ("08:00", "11:00")
    assert scheduled.schedule_needs_confirmation is False


def test_point_time_is_preserved_without_inventing_a_range() -> None:
    scheduled = apply_task_schedule_policy(
        task(
            schedule_source="natural_language",
            time_constraint_type="appointment",
            target_time="09:30",
            time_source_text="병원 예약은 9시 30분",
        ),
        request(),
    )
    assert scheduled.target_time == "09:30"
    assert scheduled.start_time is None
    assert scheduled.end_time is None
    assert scheduled.schedule_needs_confirmation is True


def test_reports_any_explicit_time_not_preserved_by_a_task() -> None:
    scheduled = task(
        schedule_source="natural_language",
        time_constraint_type="deadline",
        target_time="10:00",
    )
    assert uncovered_explicit_times(("09:30", "10:00"), [scheduled]) == {"09:30"}


def test_user_confirmed_low_risk_schedule_can_be_matched() -> None:
    confirmed = task(
        start_time="09:20",
        end_time="10:00",
        schedule_source="user_confirmed",
        time_constraint_type="deadline",
        target_time="10:00",
        schedule_needs_confirmation=False,
    )
    payload = ConfirmTaskMatchRequest(requester_name="김하늘", task=confirmed)
    assert payload.task.start_time == "09:20"
