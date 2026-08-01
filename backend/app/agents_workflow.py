from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    RunContextWrapper,
    Runner,
    function_tool,
    input_guardrail,
)
from agents.stream_events import RunItemStreamEvent
from fastapi.encoders import jsonable_encoder

from app.matching import build_assignment_plan, load_candidates
from app.models import (
    AssignmentPlan,
    CoordinatorResult,
    HelpRequest,
    SafetyAssessment,
    SafetyFinding,
    TaskPlan,
)
from app.safety import SafetyPolicyDecision, enforce_safety_policy
from app.scheduling import (
    apply_task_schedule_policy,
    extract_explicit_times,
    uncovered_explicit_times,
)

EventEmitter = Callable[[str, dict[str, object]], Awaitable[None]]
RAW_API_STREAM_LOG = Path(__file__).resolve().parents[1] / "logs" / "raw-api-stream.jsonl"


SAFETY_INSTRUCTIONS = """
당신은 생활지원 연결 서비스의 첫 번째 안전 게이트다. 작업을 만들거나 도우미를
추천하지 말고, 입력의 의미 단위별 안전 등급과 생활지원 적합성만 판정한다.

각 의미 단위를 다음 중 정확히 하나로 분류한다.
- low: 일반 이웃이 맡을 수 있는 일상 생활지원 또는 정서지원.
- mid: 작업 분해는 가능하지만 사용자 재확인 전에는 도우미를 찾으면 안 되는 요청.
  아동 등하원·이동 위탁, 요청자의 집 안으로 들어가야 하는 지원을 포함한다.
- high: 일반 이웃에게 맡기면 안 되는 요청. 약 복용·투약 관여, 침습 의료행위,
  현금·송금·결제·계좌·카드 관련 행위를 포함한다.
- emergency: 의식 없음, 쓰러짐, 출혈, 호흡 문제, 긴급 구조 등 119가 우선인 상황.
- not_actionable: 도움이 필요한 맥락이 없는 단순 편의·오락 요청.

생활지원·정서지원 판정 규칙:
- 장애, 고령, 건강, 돌봄 또는 사회적 고립 맥락이 명시된 생활·정서지원은 low다.
- "아이스크림 사주세요", "재미있는 이야기해주세요"처럼 맥락 없는 편의·오락은
  not_actionable이다.
- "거동이 어려워 식료품 구매가 필요해요"와 "혼자 지내 말벗이 필요해요"는 low다.
- 안내견을 동물병원으로 이동시키는 요청은 사람 대상 의료행위가 아니므로 low다.

혼합 입력은 문장 또는 요청 의도별로 나누어 각각 finding을 만든다. sourceText에는
판정에 필요한 최소 원문 구간과 그 요청에 연결된 예약·마감·시간 범위 표현을 빠짐없이
함께 담고, findingId는 finding-1부터 순서대로 부여한다.
모호할 때는 더 안전한 높은 등급을 선택한다. 한국어로 작성하고 구조화 출력만 반환한다.
""".strip()


PLANNER_INSTRUCTIONS = """
당신은 안전 게이트를 통과한 생활 지원 요청만 명확한 작업으로 분리하는 전문가다.

성공 기준:
- 요청을 서로 다른 도우미가 맡을 수 있는 독립 작업 1~3개로 분리한다.
- 각 작업은 짧은 제목과 구체적인 설명을 가진다.
- UI 날짜는 모든 작업의 확정 날짜로 사용한다.
- 작업에 자연어 시각이 명시되어 있으면 UI 시간보다 우선하여 반드시 보존한다.
- 자연어에 시작·종료가 모두 있는 시간 범위는 scheduleSource='natural_language',
  timeConstraintType='window'으로 설정하고 startTime과 endTime을 그대로 정규화한다.
- 예약 시각처럼 한 시점만 있으면 timeConstraintType='appointment', 마감 표현이면
  timeConstraintType='deadline'으로 설정한다. targetTime과 timeSourceText를 보존하고
  startTime/endTime은 비워 scheduleNeedsConfirmation=true로 설정한다.
- 자연어 시각이 전혀 없는 작업만 scheduleSource='ui_default'로 설정한다. 이 경우
  입력의 UI startTime/endTime을 사용하고 scheduleNeedsConfirmation=false로 설정한다.
- 불완전한 시간 범위나 이동 시간을 추정하거나 만들어내지 않는다.
- 자연어의 유용한 상황 정보는 설명에 통합하되 새로운 개인정보나 의료 사실을 만들지 않는다.
- approvedRequests에 없는 요청은 절대 작업으로 만들지 않는다.
- approvedRequests의 모든 항목을 반드시 최소 1개의 작업으로 반영한다.
- 작업은 최대 3개이므로 항목을 과도하게 세분화하지 않는다.
- 각 작업의 safetyFindingId는 근거가 된 approvedRequests의 findingId를 그대로 사용한다.
- 각 작업의 riskLevel은 해당 finding의 classification(low 또는 mid)을 그대로 사용한다.
- taskId는 task-1, task-2, task-3 순서로 부여한다.
- 한국어로 작성하고 지정된 구조화 출력만 반환한다.
""".strip()


COORDINATOR_INSTRUCTIONS = """
당신은 생활 지원 배정 흐름을 관리하는 조정 에이전트다.

반드시 다음 순서로 작업한다.
1. plan_request 도구를 정확히 한 번 호출한다.
2. 그 결과가 성공하면 match_helpers 도구를 정확히 한 번 호출한다.
3. 배정 결과를 수정하거나 후보를 직접 선택하지 않는다.
4. 두 도구가 완료되면 status='completed'인 짧은 구조화 응답을 반환한다.

후보 검색, 정렬, 중복 방지는 match_helpers의 결정론적 코드만 담당한다.
""".strip()


@dataclass
class WorkflowContext:
    request: HelpRequest
    candidates_path: Path
    emit: EventEmitter
    task_plan: TaskPlan | None = None
    assignment_plan: AssignmentPlan | None = None
    safety_decision: SafetyPolicyDecision | None = None
    emitted_messages: set[str] = field(default_factory=set)

    async def phase(self, message: str) -> None:
        if message in self.emitted_messages:
            return
        self.emitted_messages.add(message)
        await self.emit("phase", {"message": message})


def build_safety_input(request: HelpRequest) -> str:
    return (
        "다음 사용자 입력을 작업으로 분해하지 말고 안전성과 생활지원 적합성만 "
        "의미 단위별로 판정하세요.\n"
        + json.dumps({"requestText": request.request_text}, ensure_ascii=False)
    )


def build_planner_input(
    request: HelpRequest,
    approved_findings: tuple[SafetyFinding, ...],
) -> str:
    approved_source_text = "\n".join(finding.source_text for finding in approved_findings)
    payload = {
        "requesterName": request.requester_name,
        "date": request.date.isoformat(),
        "uiDefaultTime": {
            "startTime": request.start_time,
            "endTime": request.end_time,
        },
        "explicitTimes": list(extract_explicit_times(approved_source_text)),
        "approvedRequests": [
            finding.model_dump(mode="json", by_alias=True) for finding in approved_findings
        ],
    }
    return (
        "안전 게이트가 승인한 요청만 작업으로 분리하세요. UI date는 확정값이지만 "
        "UI 시간은 자연어 시각이 없는 작업에만 사용하는 기본값입니다. explicitTimes의 "
        "모든 시각을 관련 작업의 자연어 시간 필드에 반드시 보존하세요.\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def raw_tool_stream_payload(event: RunItemStreamEvent) -> dict[str, object] | None:
    """Return the full SDK raw item without selecting or rewriting its fields."""
    event_types = {
        "tool_called": "tool_call",
        "tool_output": "tool_result",
    }
    event_type = event_types.get(event.name)
    if event_type is None:
        return None

    return {
        "type": event_type,
        "sdkEvent": event.name,
        "data": jsonable_encoder(event.item.raw_item),
    }


def prepare_raw_api_stream_log(path: Path = RAW_API_STREAM_LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def reset_raw_api_stream_log(path: Path = RAW_API_STREAM_LOG) -> None:
    prepare_raw_api_stream_log(path)
    path.write_text("", encoding="utf-8")


def append_raw_api_stream_event(
    payload: dict[str, object],
    path: Path = RAW_API_STREAM_LOG,
) -> None:
    prepare_raw_api_stream_log(path)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        stream.write("\n")
        stream.flush()


def create_workflow_agents() -> Agent[WorkflowContext]:
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-terra")

    safety_agent = Agent(
        name="Safety Triage",
        instructions=SAFETY_INSTRUCTIONS,
        model=model,
        output_type=SafetyAssessment,
    )

    planner_agent = Agent(
        name="Request Planner",
        instructions=PLANNER_INSTRUCTIONS,
        model=model,
        output_type=TaskPlan,
    )

    @input_guardrail(name="생활지원 안전 게이트", run_in_parallel=False)
    async def safety_gate(
        wrapper: RunContextWrapper[WorkflowContext],
        _agent: Agent[WorkflowContext],
        _input: str | list[object],
    ) -> GuardrailFunctionOutput:
        await wrapper.context.phase("요청의 안전성과 생활지원 적합성을 먼저 확인하고 있어요.")
        result = await Runner.run(
            safety_agent,
            build_safety_input(wrapper.context.request),
            context=wrapper.context,
            max_turns=3,
        )
        assessment = result.final_output
        if not isinstance(assessment, SafetyAssessment):
            raise RuntimeError("안전성 판정 결과의 형식이 올바르지 않습니다.")

        decision = enforce_safety_policy(wrapper.context.request.request_text, assessment)
        wrapper.context.safety_decision = decision
        await wrapper.context.phase("요청의 안전성 확인을 완료했어요.")

        if decision.summary.emergency_blocked:
            await wrapper.context.phase("긴급 상황 가능성이 있어 전체 요청을 중단했어요.")
        else:
            if decision.summary.high_discarded_count:
                await wrapper.context.phase(
                    "일반 이웃에게 맡기기 어려운 요청 "
                    f"{decision.summary.high_discarded_count}개를 제외했어요."
                )
            if decision.summary.not_actionable_count:
                await wrapper.context.phase(
                    "생활·정서지원으로 보기 어려운 요청 "
                    f"{decision.summary.not_actionable_count}개를 제외했어요."
                )
            if decision.summary.mid_confirmation_count:
                await wrapper.context.phase(
                    "주의가 필요한 요청 "
                    f"{decision.summary.mid_confirmation_count}개는 확인 후 도우미를 찾아요."
                )

        return GuardrailFunctionOutput(
            output_info=decision.assessment.model_dump(mode="json", by_alias=True),
            tripwire_triggered=decision.should_stop,
        )

    @function_tool
    async def plan_request(wrapper: RunContextWrapper[WorkflowContext]) -> str:
        """Split the current request into one to three structured helper tasks."""
        if wrapper.context.safety_decision is None:
            raise RuntimeError("작업 분석 전에 안전성 확인이 필요합니다.")
        await wrapper.context.phase("요청 내용을 확인하고 있어요.")
        approved_findings = wrapper.context.safety_decision.allowed_findings[:3]
        planner_input = build_planner_input(wrapper.context.request, approved_findings)
        explicit_times_by_finding = {
            finding.finding_id: extract_explicit_times(finding.source_text)
            for finding in approved_findings
        }

        def missing_schedule_times(task_plan: TaskPlan) -> set[str]:
            return {
                time
                for finding_id, finding_times in explicit_times_by_finding.items()
                for time in uncovered_explicit_times(
                    finding_times,
                    (
                        task
                        for task in task_plan.tasks
                        if task.safety_finding_id == finding_id
                    ),
                )
            }
        allowed_levels = {
            finding.finding_id: finding.classification
            for finding in approved_findings
        }

        async def run_planner(current_input: str) -> TaskPlan:
            result = await Runner.run(
                planner_agent,
                current_input,
                context=wrapper.context,
                max_turns=3,
            )
            output = result.final_output
            if not isinstance(output, TaskPlan):
                raise RuntimeError("요청 분석 결과의 형식이 올바르지 않습니다.")
            normalized_tasks = []
            for task in output.tasks:
                expected_level = allowed_levels.get(task.safety_finding_id)
                if expected_level not in {"low", "mid"}:
                    raise RuntimeError("안전 게이트에서 승인하지 않은 작업이 포함됐습니다.")
                normalized_tasks.append(
                    apply_task_schedule_policy(
                        task.model_copy(update={"risk_level": expected_level}),
                        wrapper.context.request,
                    )
                )
            return output.model_copy(update={"tasks": normalized_tasks})

        task_plan = await run_planner(planner_input)
        covered_ids = {task.safety_finding_id for task in task_plan.tasks}
        missing_ids = set(allowed_levels) - covered_ids
        missing_times = missing_schedule_times(task_plan)
        if missing_ids or missing_times:
            await wrapper.context.phase("누락된 요청과 시간 정보를 다시 확인하고 있어요.")
            retry_requirements = []
            if missing_ids:
                retry_requirements.append(
                    "다음 findingId를 각각 반드시 작업에 포함하세요: "
                    + ", ".join(sorted(missing_ids))
                )
            if missing_times:
                retry_requirements.append(
                    "다음 자연어 시각을 관련 작업에 반드시 보존하세요: "
                    + ", ".join(sorted(missing_times))
                )
            task_plan = await run_planner(
                planner_input
                + "\n이전 결과에 누락이 있습니다. "
                + " ".join(retry_requirements)
            )
            covered_ids = {task.safety_finding_id for task in task_plan.tasks}
            if set(allowed_levels) - covered_ids:
                raise RuntimeError("안전 게이트가 승인한 요청을 모두 작업으로 만들지 못했습니다.")
            missing_times = missing_schedule_times(task_plan)
            if missing_times:
                raise RuntimeError("자연어에 명시된 작업 시각을 모두 보존하지 못했습니다.")
        wrapper.context.task_plan = task_plan
        await wrapper.context.phase(f"{len(task_plan.tasks)}개의 작업이 필요한 것으로 파악했어요.")
        if any(task.schedule_needs_confirmation for task in task_plan.tasks):
            await wrapper.context.phase("시작·종료 확인이 필요한 작업 시간을 보존했어요.")
        else:
            await wrapper.context.phase("작업별 날짜와 시간을 적용했어요.")
        return task_plan.model_dump_json(by_alias=True)

    @function_tool
    async def match_helpers(wrapper: RunContextWrapper[WorkflowContext]) -> str:
        """Match distinct available helpers using distance and completed-help count."""
        if wrapper.context.task_plan is None:
            raise RuntimeError("도우미 검색 전에 요청 분석이 필요합니다.")
        if wrapper.context.safety_decision is None:
            raise RuntimeError("도우미 검색 전에 안전성 확인이 필요합니다.")
        low_task_ids = {
            task.task_id
            for task in wrapper.context.task_plan.tasks
            if task.risk_level == "low" and not task.schedule_needs_confirmation
        }
        candidates = []
        if low_task_ids:
            await wrapper.context.phase("해당 시간에 가능한 도우미를 찾고 있어요.")
            candidates = load_candidates(wrapper.context.candidates_path)
        else:
            await wrapper.context.phase("주의 요청은 사용자 확인 전 도우미를 찾지 않아요.")
        assignment_plan = build_assignment_plan(
            requester_name=wrapper.context.request.requester_name,
            task_plan=wrapper.context.task_plan,
            candidates=candidates,
            search_task_ids=low_task_ids,
            safety=wrapper.context.safety_decision.summary,
        )
        wrapper.context.assignment_plan = assignment_plan
        if low_task_ids:
            await wrapper.context.phase(
                f"{len(candidates)}명의 후보 중 거리와 도움 경험을 기준으로 배정했어요."
            )
        return assignment_plan.model_dump_json(by_alias=True)

    return Agent[WorkflowContext](
        name="Welfare Request Coordinator",
        instructions=COORDINATOR_INSTRUCTIONS,
        model=model,
        tools=[plan_request, match_helpers],
        output_type=CoordinatorResult,
        input_guardrails=[safety_gate],
    )


async def run_workflow(
    request: HelpRequest,
    candidates_path: Path,
    emit: EventEmitter,
) -> AssignmentPlan:
    reset_raw_api_stream_log()
    context = WorkflowContext(request=request, candidates_path=candidates_path, emit=emit)
    await context.phase("도움 요청을 접수했어요.")

    coordinator = create_workflow_agents()
    stream = Runner.run_streamed(
        coordinator,
        "안전 게이트를 먼저 실행한 뒤 승인된 요청만 분석하고 도우미를 배정하세요.",
        context=context,
        max_turns=8,
    )

    try:
        async for event in stream.stream_events():
            # Raw tool events are written verbatim to the judge-facing JSONL log,
            # while the user interface continues to receive only public phase events.
            if not isinstance(event, RunItemStreamEvent):
                continue
            payload = raw_tool_stream_payload(event)
            if payload is not None:
                append_raw_api_stream_event(payload)
    except InputGuardrailTripwireTriggered:
        if context.safety_decision is None:
            raise RuntimeError("안전 게이트가 요청 처리를 중단했습니다.") from None
        if context.safety_decision.summary.emergency_blocked:
            await context.phase("119로 즉시 도움을 요청해주세요.")
        else:
            await context.phase("도우미 검색 없이 요청 처리를 마쳤어요.")
        return AssignmentPlan(
            request_summary=context.safety_decision.assessment.summary,
            tasks=[],
            assignments=[],
            candidate_queues=[],
            unassigned_task_ids=[],
            safety=context.safety_decision.summary,
        )

    if context.assignment_plan is None:
        raise RuntimeError("에이전트가 도우미 배정 단계를 완료하지 못했습니다.")

    schedule_confirmation_count = sum(
        task.schedule_needs_confirmation for task in context.assignment_plan.tasks
    )
    if context.assignment_plan.safety.mid_confirmation_count or schedule_confirmation_count:
        await context.phase("일반 요청의 추천을 완료하고 확인이 필요한 요청을 기다려요.")
    else:
        await context.phase("도우미 추천을 완료했어요.")
    return context.assignment_plan
