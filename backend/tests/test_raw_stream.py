import json
from types import SimpleNamespace

from app.agents_workflow import (
    append_raw_api_stream_event,
    raw_tool_stream_payload,
    reset_raw_api_stream_log,
)


def test_preserves_raw_tool_call_item() -> None:
    raw_item = {
        "type": "function_call",
        "call_id": "call_demo",
        "name": "plan_request",
        "arguments": '{"request":"demo"}',
    }
    event = SimpleNamespace(name="tool_called", item=SimpleNamespace(raw_item=raw_item))

    assert raw_tool_stream_payload(event) == {
        "type": "tool_call",
        "sdkEvent": "tool_called",
        "data": raw_item,
    }


def test_preserves_raw_tool_result_item() -> None:
    raw_item = {
        "type": "function_call_output",
        "call_id": "call_demo",
        "output": '{"status":"ok"}',
    }
    event = SimpleNamespace(name="tool_output", item=SimpleNamespace(raw_item=raw_item))

    assert raw_tool_stream_payload(event) == {
        "type": "tool_result",
        "sdkEvent": "tool_output",
        "data": raw_item,
    }


def test_ignores_non_tool_stream_items() -> None:
    event = SimpleNamespace(name="message_output_created", item=SimpleNamespace(raw_item={}))

    assert raw_tool_stream_payload(event) is None


def test_writes_each_raw_event_as_a_flushed_json_line(tmp_path) -> None:
    log_path = tmp_path / "raw-api-stream.jsonl"
    payload = {
        "type": "tool_call",
        "sdkEvent": "tool_called",
        "data": {"type": "function_call", "name": "plan_request"},
    }

    reset_raw_api_stream_log(log_path)
    append_raw_api_stream_event(payload, log_path)

    assert [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()] == [
        payload
    ]
