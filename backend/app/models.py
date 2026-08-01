from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

TimeText = Annotated[str, StringConstraints(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
SafetyClassification = Literal["low", "mid", "high", "emergency", "not_actionable"]
TaskRiskLevel = Literal["low", "mid"]


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
    start_time: TimeText
    end_time: TimeText
    risk_level: TaskRiskLevel


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


class ConfirmMidMatchRequest(ApiModel):
    requester_name: str = Field(min_length=1, max_length=40)
    task: PlannedTask
    excluded_candidate_ids: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_mid_task(self) -> ConfirmMidMatchRequest:
        if self.task.risk_level != "mid":
            raise ValueError("주의 요청으로 분류된 작업만 다시 확인할 수 있습니다.")
        return self


class CoordinatorResult(ApiModel):
    status: Literal["completed"]
    message: str = Field(max_length=120)


class PhaseEvent(ApiModel):
    message: str


class HealthResponse(ApiModel):
    status: Literal["ok"]
