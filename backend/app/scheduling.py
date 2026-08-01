from __future__ import annotations

import re
from collections.abc import Iterable

from app.models import HelpRequest, PlannedTask

COLON_TIME_PATTERN = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
KOREAN_TIME_PATTERN = re.compile(
    r"(?:(오전|오후)\s*)?([01]?\d|2[0-3])\s*시"
    r"(?:\s*(?:([0-5]?\d)\s*분|(반)))?"
)


def _normalize_korean_time(
    period: str | None,
    hour_text: str,
    minute_text: str | None,
    half: str | None,
) -> str:
    hour = int(hour_text)
    minute = 30 if half else int(minute_text or "0")
    if period == "오전" and hour == 12:
        hour = 0
    elif period == "오후" and hour < 12:
        hour += 12
    return f"{hour:02d}:{minute:02d}"


def extract_explicit_times(text: str) -> tuple[str, ...]:
    """Extract explicit clock times in source order without inferring missing ranges."""
    matches: list[tuple[int, str]] = []
    matches.extend(
        (match.start(), f"{int(match.group(1)):02d}:{int(match.group(2)):02d}")
        for match in COLON_TIME_PATTERN.finditer(text)
    )
    matches.extend(
        (
            match.start(),
            _normalize_korean_time(
                match.group(1),
                match.group(2),
                match.group(3),
                match.group(4),
            ),
        )
        for match in KOREAN_TIME_PATTERN.finditer(text)
    )

    ordered: list[str] = []
    for _, value in sorted(matches):
        if value not in ordered:
            ordered.append(value)
    return tuple(ordered)


def apply_task_schedule_policy(task: PlannedTask, request: HelpRequest) -> PlannedTask:
    """Apply UI time only as a fallback and never invent a range for point constraints."""
    updates: dict[str, object] = {"date": request.date}
    if task.schedule_source == "ui_default":
        updates.update(
            start_time=request.start_time,
            end_time=request.end_time,
            target_time=None,
            time_source_text=None,
            time_constraint_type="window",
            schedule_needs_confirmation=False,
        )
    elif task.time_constraint_type in {"appointment", "deadline"}:
        updates.update(
            start_time=None,
            end_time=None,
            schedule_needs_confirmation=True,
        )
    elif task.start_time is None or task.end_time is None:
        updates["schedule_needs_confirmation"] = True
    else:
        updates["schedule_needs_confirmation"] = False
    return task.model_copy(update=updates)


def uncovered_explicit_times(
    explicit_times: Iterable[str],
    tasks: Iterable[PlannedTask],
) -> set[str]:
    preserved = {
        value
        for task in tasks
        for value in (task.start_time, task.end_time, task.target_time)
        if value is not None and task.schedule_source == "natural_language"
    }
    return set(explicit_times) - preserved
