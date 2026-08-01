from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.agents_workflow import prepare_raw_api_stream_log, run_workflow
from app.matching import build_confirmed_task_queue, load_candidates
from app.models import ConfirmTaskMatchRequest, HealthResponse, HelpRequest, TaskCandidateQueue

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
CANDIDATES_PATH = BACKEND_DIR / "data" / "helper-users.json"

load_dotenv(ROOT_DIR / ".env", override=False)

logger = logging.getLogger("welfare-helper-demo")

app = FastAPI(title="Welfare Helper Agent Demo", version="0.1.0")

configured_origins = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
origins = {
    configured_origins,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def encode_sse(event: str, data: dict[str, object]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/requests/stream")
async def stream_request(request: HelpRequest) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, dict[str, object]] | None] = asyncio.Queue()

        async def emit(event: str, data: dict[str, object]) -> None:
            await queue.put((event, data))

        async def execute() -> None:
            try:
                if not os.getenv("OPENAI_API_KEY"):
                    raise RuntimeError("OpenAI API 설정을 확인해주세요.")
                plan = await run_workflow(request, CANDIDATES_PATH, emit)
                await emit("result", plan.model_dump(mode="json", by_alias=True))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Agent workflow failed: %s", type(exc).__name__)
                message = (
                    str(exc)
                    if isinstance(exc, RuntimeError)
                    else "요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요."
                )
                await emit("error", {"message": message})
            finally:
                await queue.put(None)

        task = asyncio.create_task(execute())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event, data = item
                yield encode_sse(event, data)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/tasks/confirm-match", response_model=TaskCandidateQueue)
async def confirm_task(request: ConfirmTaskMatchRequest) -> TaskCandidateQueue:
    candidates = load_candidates(CANDIDATES_PATH)
    return build_confirmed_task_queue(
        requester_name=request.requester_name,
        task=request.task,
        candidates=candidates,
        excluded_candidate_ids=set(request.excluded_candidate_ids),
    )


def run() -> None:
    prepare_raw_api_stream_log()
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)
