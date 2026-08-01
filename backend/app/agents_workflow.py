from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from agents import Agent, RunContextWrapper, Runner, function_tool

from app.matching import build_assignment_plan, load_candidates
from app.models import AssignmentPlan, CoordinatorResult, HelpRequest, TaskPlan

EventEmitter = Callable[[str, dict[str, object]], Awaitable[None]]


PLANNER_INSTRUCTIONS = """
당신은 생활 지원 요청을 안전하고 명확한 작업으로 분리하는 요청 분석 전문가다.

성공 기준:
- 요청을 서로 다른 도우미가 맡을 수 있는 독립 작업 1~3개로 분리한다.
- 각 작업은 짧은 제목과 구체적인 설명을 가진다.
- 입력에 제공된 UI 날짜, 시작 시간, 종료 시간을 모든 작업에 그대로 사용한다.
- 자연어 속 날짜나 시간이 UI 값과 충돌해도 절대 UI 값을 변경하지 않는다.
- 자연어의 유용한 상황 정보는 설명에 통합하되 새로운 개인정보나 의료 사실을 만들지 않는다.
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
    emitted_messages: set[str] = field(default_factory=set)

    async def phase(self, message: str) -> None:
        if message in self.emitted_messages:
            return
        self.emitted_messages.add(message)
        await self.emit("phase", {"message": message})


def build_planner_input(request: HelpRequest) -> str:
    payload = request.model_dump(mode="json", by_alias=True)
    return (
        "다음 요청을 작업으로 분리하세요. UI에서 선택된 date, startTime, endTime은 "
        "자연어보다 우선하는 확정값입니다.\n" + json.dumps(payload, ensure_ascii=False)
    )


def create_workflow_agents() -> Agent[WorkflowContext]:
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-terra")

    planner_agent = Agent(
        name="Request Planner",
        instructions=PLANNER_INSTRUCTIONS,
        model=model,
        output_type=TaskPlan,
    )

    @function_tool
    async def plan_request(wrapper: RunContextWrapper[WorkflowContext]) -> str:
        """Split the current request into one to three structured helper tasks."""
        await wrapper.context.phase("요청 내용을 확인하고 있어요.")
        result = await Runner.run(
            planner_agent,
            build_planner_input(wrapper.context.request),
            context=wrapper.context,
            max_turns=3,
        )
        task_plan = result.final_output
        if not isinstance(task_plan, TaskPlan):
            raise RuntimeError("요청 분석 결과의 형식이 올바르지 않습니다.")
        wrapper.context.task_plan = task_plan
        await wrapper.context.phase(f"{len(task_plan.tasks)}개의 작업이 필요한 것으로 파악했어요.")
        await wrapper.context.phase("선택한 날짜와 시간을 작업에 적용했어요.")
        return task_plan.model_dump_json(by_alias=True)

    @function_tool
    async def match_helpers(wrapper: RunContextWrapper[WorkflowContext]) -> str:
        """Match distinct available helpers using distance and completed-help count."""
        if wrapper.context.task_plan is None:
            raise RuntimeError("도우미 검색 전에 요청 분석이 필요합니다.")
        await wrapper.context.phase("해당 시간에 가능한 도우미를 찾고 있어요.")
        candidates = load_candidates(wrapper.context.candidates_path)
        assignment_plan = build_assignment_plan(
            requester_name=wrapper.context.request.requester_name,
            task_plan=wrapper.context.task_plan,
            candidates=candidates,
        )
        wrapper.context.assignment_plan = assignment_plan
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
    )


async def run_workflow(
    request: HelpRequest,
    candidates_path: Path,
    emit: EventEmitter,
) -> AssignmentPlan:
    context = WorkflowContext(request=request, candidates_path=candidates_path, emit=emit)
    await context.phase("도움 요청을 접수했어요.")

    coordinator = create_workflow_agents()
    stream = Runner.run_streamed(
        coordinator,
        (
            "현재 요청을 분석하고 도우미를 배정하세요. UI 입력값은 다음과 같습니다.\n"
            + json.dumps(request.model_dump(mode="json", by_alias=True), ensure_ascii=False)
        ),
        context=context,
        max_turns=8,
    )

    async for _event in stream.stream_events():
        # Raw model events are intentionally not forwarded to the user interface.
        pass

    if context.assignment_plan is None:
        raise RuntimeError("에이전트가 도우미 배정 단계를 완료하지 못했습니다.")

    await context.phase("도우미 추천을 완료했어요.")
    return context.assignment_plan
