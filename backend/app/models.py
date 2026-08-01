from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

TimeText = Annotated[str, StringConstraints(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
SafetyClassification = Literal["low", "mid", "high", "emergency", "not_actionable"]
TaskRiskLevel = Literal["low", "mid"]
ScheduleSource = Literal["ui_default", "natural_language", "user_confirmed"]
TimeConstraintType = Literal["window", "appointment", "deadline"]


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class HelpRequest(ApiModel):
    requester_name: str = Field(min_length=1, max_length=40)
    request_text: str = Field(min_length=5, max_length=1200)
    date: date
    start_time: TimeText
    end_time: TimeText

    @model_validator(mode="after")
    def validate_time_range(self) -> HelpRequest:
        if self.start_time >= self.end_time:
            raise ValueError("종료 시간은 시작 시간보다 늦어야 합니다.")
        return self


class SafetyFinding(ApiModel):
    finding_id: str = Field(min_length=1, max_length=40)
    source_text: str = Field(min_length=1, max_length=400)
    classification: SafetyClassification
    category: str = Field(min_length=1, max_length=60)
    reason: str = Field(min_length=1, max_length=240)


class SafetyAssessment(ApiModel):
    summary: str = Field(min_length=1, max_length=240)
    findings: list[SafetyFinding] = Field(min_length=1, max_length=8)


class SafetySummary(ApiModel):
    highest_classification: SafetyClassification = "low"
    emergency_blocked: bool = False
    high_discarded_count: int = Field(default=0, ge=0)
    not_actionable_count: int = Field(default=0, ge=0)
    mid_confirmation_count: int = Field(default=0, ge=0)


class PlannedTask(ApiModel):
    task_id: str = Field(min_length=1, max_length=40)
    safety_finding_id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=300)
    date: date
    start_time: TimeText | None = None
    end_time: TimeText | None = None
    risk_level: TaskRiskLevel
    schedule_source: ScheduleSource = "ui_default"
    time_constraint_type: TimeConstraintType = "window"
    target_time: TimeText | None = None
    time_source_text: str | None = Field(default=None, max_length=200)
    schedule_needs_confirmation: bool = False

    @model_validator(mode="after")
    def validate_schedule(self) -> PlannedTask:
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("작업 시작 시간과 종료 시간은 함께 입력해야 합니다.")
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time >= self.end_time
        ):
            raise ValueError("작업 종료 시간은 시작 시간보다 늦어야 합니다.")
        return self


class TaskPlan(ApiModel):
    request_summary: str = Field(min_length=1, max_length=240)
    tasks: list[PlannedTask] = Field(min_length=1, max_length=3)


class AvailabilityRange(ApiModel):
    start_time: TimeText
    end_time: TimeText


class HelperCandidate(ApiModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    candidate_id: str
    display_name: str
    availability_time_ranges: list[AvailabilityRange]
    distance_meters: int = Field(ge=0)
    completed_help_count: int = Field(ge=0)


class CandidateCollection(ApiModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    candidates: list[HelperCandidate]


class HelperSummary(ApiModel):
    candidate_id: str
    display_name: str
    distance_meters: int
    completed_help_count: int


class Assignment(ApiModel):
    task: PlannedTask
    helper: HelperSummary
    invitation_message: str


class CandidateOption(ApiModel):
    helper: HelperSummary
    invitation_message: str


class TaskCandidateQueue(ApiModel):
    task: PlannedTask
    candidates: list[CandidateOption] = Field(max_length=2)


class AssignmentPlan(ApiModel):
    request_summary: str
    tasks: list[PlannedTask] = Field(max_length=3)
    assignments: list[Assignment] = Field(max_length=3)
    candidate_queues: list[TaskCandidateQueue] = Field(max_length=3)
    unassigned_task_ids: list[str]
    safety: SafetySummary = Field(default_factory=SafetySummary)


class ConfirmTaskMatchRequest(ApiModel):
    requester_name: str = Field(min_length=1, max_length=40)
    task: PlannedTask
    excluded_candidate_ids: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_confirmed_schedule(self) -> ConfirmTaskMatchRequest:
        if self.task.start_time is None or self.task.end_time is None:
            raise ValueError("도우미를 찾기 전에 작업 시간을 확인해야 합니다.")
        if self.task.schedule_needs_confirmation:
            raise ValueError("확인되지 않은 작업 시간으로는 도우미를 찾을 수 없습니다.")
        if self.task.risk_level != "mid" and self.task.schedule_source != "user_confirmed":
            raise ValueError("사용자 확인이 필요한 작업만 다시 매칭할 수 있습니다.")
        return self


class CoordinatorResult(ApiModel):
    status: Literal["completed"]
    message: str = Field(max_length=120)


class PhaseEvent(ApiModel):
    message: str


class HealthResponse(ApiModel):
    status: Literal["ok"]
