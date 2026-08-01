from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from app.models import (
    Assignment,
    AssignmentPlan,
    CandidateCollection,
    CandidateOption,
    HelperCandidate,
    HelperSummary,
    PlannedTask,
    SafetySummary,
    TaskCandidateQueue,
    TaskPlan,
)


def load_candidates(path: Path) -> list[HelperCandidate]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return CandidateCollection.model_validate(raw).candidates


def is_available(candidate: HelperCandidate, task: PlannedTask) -> bool:
    return any(
        availability.start_time <= task.start_time and task.end_time <= availability.end_time
        for availability in candidate.availability_time_ranges
    )


def candidate_rank(candidate: HelperCandidate) -> tuple[int, int, str]:
    return (
        candidate.distance_meters,
        -candidate.completed_help_count,
        candidate.candidate_id,
    )


def _assignment_score(
    selected: Sequence[HelperCandidate | None],
) -> tuple[int, int, int, tuple[str, ...]]:
    assigned = [candidate for candidate in selected if candidate is not None]
    return (
        -len(assigned),
        sum(candidate.distance_meters for candidate in assigned),
        -sum(candidate.completed_help_count for candidate in assigned),
        tuple(candidate.candidate_id if candidate else "~" for candidate in selected),
    )


def choose_helpers(
    tasks: Sequence[PlannedTask],
    candidates: Sequence[HelperCandidate],
) -> list[HelperCandidate | None]:
    limited_tasks = list(tasks[:3])
    feasible = [
        sorted(
            (candidate for candidate in candidates if is_available(candidate, task)),
            key=candidate_rank,
        )
        for task in limited_tasks
    ]

    best: list[HelperCandidate | None] | None = None
    best_score: tuple[int, int, int, tuple[str, ...]] | None = None

    def search(
        task_index: int,
        selected: list[HelperCandidate | None],
        used_ids: set[str],
    ) -> None:
        nonlocal best, best_score

        if task_index == len(limited_tasks):
            score = _assignment_score(selected)
            if best_score is None or score < best_score:
                best = list(selected)
                best_score = score
            return

        for candidate in feasible[task_index]:
            if candidate.candidate_id in used_ids:
                continue
            selected.append(candidate)
            used_ids.add(candidate.candidate_id)
            search(task_index + 1, selected, used_ids)
            used_ids.remove(candidate.candidate_id)
            selected.pop()

        selected.append(None)
        search(task_index + 1, selected, used_ids)
        selected.pop()

    search(0, [], set())
    return best or [None] * len(limited_tasks)


def build_assignment_plan(
    requester_name: str,
    task_plan: TaskPlan,
    candidates: Sequence[HelperCandidate],
    *,
    search_task_ids: set[str] | None = None,
    safety: SafetySummary | None = None,
) -> AssignmentPlan:
    tasks = task_plan.tasks[:3]
    searchable_ids = search_task_ids or {
        task.task_id for task in tasks if task.risk_level == "low"
    }
    searchable_tasks = [task for task in tasks if task.task_id in searchable_ids]
    first_round = choose_helpers(searchable_tasks, candidates)
    first_round_ids = {candidate.candidate_id for candidate in first_round if candidate is not None}
    remaining_candidates = [
        candidate for candidate in candidates if candidate.candidate_id not in first_round_ids
    ]
    second_round = choose_helpers(searchable_tasks, remaining_candidates)
    first_by_task = dict(zip((task.task_id for task in searchable_tasks), first_round, strict=True))
    second_by_task = dict(
        zip((task.task_id for task in searchable_tasks), second_round, strict=True)
    )
    assignments: list[Assignment] = []
    candidate_queues: list[TaskCandidateQueue] = []
    unassigned_task_ids: list[str] = []

    for task in tasks:
        if task.task_id not in searchable_ids:
            candidate_queues.append(TaskCandidateQueue(task=task, candidates=[]))
            continue

        first_candidate = first_by_task[task.task_id]
        second_candidate = second_by_task[task.task_id]
        queue_candidates = [
            candidate for candidate in (first_candidate, second_candidate) if candidate is not None
        ]

        candidate_options = [
            CandidateOption(
                helper=HelperSummary(
                    candidate_id=candidate.candidate_id,
                    display_name=candidate.display_name,
                    distance_meters=candidate.distance_meters,
                    completed_help_count=candidate.completed_help_count,
                ),
                invitation_message=f"{requester_name}님이 도움을 요청했어요!",
            )
            for candidate in queue_candidates
        ]
        candidate_queues.append(TaskCandidateQueue(task=task, candidates=candidate_options))

        if first_candidate is None:
            unassigned_task_ids.append(task.task_id)
            continue

        assignments.append(
            Assignment(
                task=task,
                helper=HelperSummary(
                    candidate_id=first_candidate.candidate_id,
                    display_name=first_candidate.display_name,
                    distance_meters=first_candidate.distance_meters,
                    completed_help_count=first_candidate.completed_help_count,
                ),
                invitation_message=f"{requester_name}님이 도움을 요청했어요!",
            )
        )

    return AssignmentPlan(
        request_summary=task_plan.request_summary,
        tasks=tasks,
        assignments=assignments,
        candidate_queues=candidate_queues,
        unassigned_task_ids=unassigned_task_ids,
        safety=safety or SafetySummary(),
    )


def build_confirmed_mid_queue(
    requester_name: str,
    task: PlannedTask,
    candidates: Sequence[HelperCandidate],
    excluded_candidate_ids: set[str],
) -> TaskCandidateQueue:
    eligible_candidates = [
        candidate
        for candidate in candidates
        if candidate.candidate_id not in excluded_candidate_ids
    ]
    plan = build_assignment_plan(
        requester_name,
        TaskPlan(request_summary=task.title, tasks=[task]),
        eligible_candidates,
        search_task_ids={task.task_id},
    )
    return plan.candidate_queues[0]
