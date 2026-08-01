from datetime import date

from app.matching import (
    build_assignment_plan,
    build_confirmed_mid_queue,
    choose_helpers,
    is_available,
)
from app.models import (
    AvailabilityRange,
    HelperCandidate,
    PlannedTask,
    TaskPlan,
)


def task(task_id: str = "task-1", start: str = "08:00", end: str = "09:00") -> PlannedTask:
    return PlannedTask(
        task_id=task_id,
        safety_finding_id=f"finding-{task_id}",
        title=f"작업 {task_id}",
        description="도움이 필요한 작업",
        date=date(2026, 8, 3),
        start_time=start,
        end_time=end,
        risk_level="low",
    )


def candidate(
    candidate_id: str,
    distance: int,
    completed: int,
    start: str = "08:00",
    end: str = "12:00",
) -> HelperCandidate:
    return HelperCandidate(
        candidate_id=candidate_id,
        display_name=f"도우미 {candidate_id}",
        availability_time_ranges=[AvailabilityRange(start_time=start, end_time=end)],
        distance_meters=distance,
        completed_help_count=completed,
    )


def test_availability_must_cover_the_entire_task() -> None:
    helper = candidate("a", 100, 1, start="08:30", end="09:30")
    assert not is_available(helper, task(start="08:00", end="09:00"))
    assert is_available(helper, task(start="08:30", end="09:30"))


def test_distance_then_completed_count_determine_rank() -> None:
    helpers = [
        candidate("far", 200, 100),
        candidate("near-low", 100, 2),
        candidate("near-high", 100, 20),
    ]
    selected = choose_helpers([task()], helpers)
    assert selected[0] is not None
    assert selected[0].candidate_id == "near-high"


def test_distinct_helpers_are_assigned_to_distinct_tasks() -> None:
    helpers = [candidate("a", 100, 10), candidate("b", 200, 20)]
    selected = choose_helpers([task("task-1"), task("task-2")], helpers)
    assert {helper.candidate_id for helper in selected if helper} == {"a", "b"}


def test_maximum_coverage_wins_before_distance() -> None:
    flexible = candidate("flexible", 100, 10, start="08:00", end="12:00")
    morning_only = candidate("morning", 200, 10, start="08:00", end="09:00")
    selected = choose_helpers(
        [task("morning-task", "08:00", "09:00"), task("late-task", "10:00", "11:00")],
        [flexible, morning_only],
    )
    assert selected[0] is not None and selected[0].candidate_id == "morning"
    assert selected[1] is not None and selected[1].candidate_id == "flexible"


def test_unassigned_task_is_reported_without_inventing_helper() -> None:
    plan = build_assignment_plan(
        "김하늘",
        TaskPlan(request_summary="요약", tasks=[task()]),
        [candidate("late", 100, 1, start="10:00", end="11:00")],
    )
    assert plan.assignments == []
    assert plan.candidate_queues[0].candidates == []
    assert plan.unassigned_task_ids == ["task-1"]


def test_each_task_reserves_at_most_two_distinct_candidates() -> None:
    helpers = [
        candidate("a", 100, 10),
        candidate("b", 200, 20),
        candidate("c", 300, 30),
        candidate("d", 400, 40),
    ]
    plan = build_assignment_plan(
        "김하늘",
        TaskPlan(request_summary="요약", tasks=[task("task-1"), task("task-2")]),
        helpers,
    )
    option_ids = [
        option.helper.candidate_id for queue in plan.candidate_queues for option in queue.candidates
    ]
    assert all(len(queue.candidates) <= 2 for queue in plan.candidate_queues)
    assert len(option_ids) == len(set(option_ids)) == 4


def test_mid_task_is_not_searched_before_confirmation() -> None:
    mid_task = task().model_copy(update={"risk_level": "mid"})
    plan = build_assignment_plan(
        "김하늘",
        TaskPlan(request_summary="요약", tasks=[mid_task]),
        [candidate("a", 100, 10)],
    )
    assert plan.candidate_queues[0].candidates == []
    assert plan.unassigned_task_ids == []


def test_confirmed_mid_task_searches_two_new_candidates() -> None:
    mid_task = task().model_copy(update={"risk_level": "mid"})
    queue = build_confirmed_mid_queue(
        "김하늘",
        mid_task,
        [candidate("used", 50, 30), candidate("a", 100, 10), candidate("b", 200, 20)],
        {"used"},
    )
    assert [option.helper.candidate_id for option in queue.candidates] == ["a", "b"]
