from app.models import SafetyAssessment, SafetyFinding
from app.safety import enforce_safety_policy


def finding(
    source_text: str,
    classification: str = "low",
    finding_id: str = "finding-1",
) -> SafetyFinding:
    return SafetyFinding(
        finding_id=finding_id,
        source_text=source_text,
        classification=classification,
        category="test",
        reason="테스트 판정",
    )


def assessment(*findings: SafetyFinding) -> SafetyAssessment:
    return SafetyAssessment(summary="안전성 판정", findings=list(findings))


def test_emergency_rule_blocks_the_entire_request() -> None:
    decision = enforce_safety_policy(
        "출근 준비를 도와주세요. 갑자기 쓰러져 의식이 없어요.",
        assessment(
            finding("출근 준비를 도와주세요.", "low", "finding-1"),
            finding("갑자기 쓰러져 의식이 없어요.", "low", "finding-2"),
        ),
    )
    assert decision.summary.emergency_blocked is True
    assert decision.should_stop is True
    assert decision.allowed_findings == (decision.assessment.findings[0],)


def test_high_request_is_discarded_while_low_request_continues() -> None:
    decision = enforce_safety_policy(
        "출근 준비를 도와주세요. 약을 먹여주세요.",
        assessment(
            finding("출근 준비를 도와주세요.", "low", "finding-1"),
            finding("약을 먹여주세요.", "low", "finding-2"),
        ),
    )
    assert [item.finding_id for item in decision.allowed_findings] == ["finding-1"]
    assert [item.finding_id for item in decision.high_findings] == ["finding-2"]
    assert decision.should_stop is False


def test_mid_rule_requires_confirmation() -> None:
    decision = enforce_safety_policy(
        "아이를 학교에 데려다주세요.",
        assessment(finding("아이를 학교에 데려다주세요.")),
    )
    assert decision.allowed_findings[0].classification == "mid"
    assert decision.summary.mid_confirmation_count == 1


def test_only_non_actionable_content_stops_before_planning() -> None:
    decision = enforce_safety_policy(
        "재미있는 이야기해주세요.",
        assessment(finding("재미있는 이야기해주세요.", "not_actionable")),
    )
    assert decision.summary.not_actionable_count == 1
    assert decision.should_stop is True
