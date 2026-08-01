from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import SafetyAssessment, SafetyClassification, SafetyFinding, SafetySummary

RISK_ORDER: dict[SafetyClassification, int] = {
    "not_actionable": 0,
    "low": 1,
    "mid": 2,
    "high": 3,
    "emergency": 4,
}

EMERGENCY_PATTERNS = (
    re.compile(r"의식(?:이)?\s*(?:없|잃)"),
    re.compile(r"쓰러(?:졌|짐|진|져)"),
    re.compile(r"출혈|피가\s*(?:멈추지|많이)"),
    re.compile(r"호흡\s*(?:곤란|정지)|숨을\s*(?:못|안\s*쉬)"),
    re.compile(r"심정지|긴급\s*구조|119"),
)

HIGH_PATTERNS = (
    re.compile(r"약\s*(?:을\s*)?(?:먹|복용|투여)|투약|복약"),
    re.compile(r"주사|침습|봉합|카테터|관장|상처\s*처치"),
    re.compile(
        r"현금|송금|결제|계좌\s*이체|카드\s*(?:번호|비밀번호)|"
        r"돈\s*(?:보내|찾아|인출|빌려)"
    ),
)

MID_PATTERNS = (
    re.compile(r"(?:아이|아동|어린이).{0,16}(?:등교|하교|등하원|등원|하원|데려다)"),
    re.compile(r"(?:집|가정|주거지)\s*(?:안|내부|안으로).{0,16}(?:들어|입장|출입)"),
)


@dataclass(frozen=True)
class SafetyPolicyDecision:
    assessment: SafetyAssessment
    allowed_findings: tuple[SafetyFinding, ...]
    high_findings: tuple[SafetyFinding, ...]
    excluded_findings: tuple[SafetyFinding, ...]
    emergency_findings: tuple[SafetyFinding, ...]
    summary: SafetySummary

    @property
    def should_stop(self) -> bool:
        return bool(self.emergency_findings) or not self.allowed_findings


def _rule_classification(text: str) -> SafetyClassification | None:
    if any(pattern.search(text) for pattern in EMERGENCY_PATTERNS):
        return "emergency"
    if any(pattern.search(text) for pattern in HIGH_PATTERNS):
        return "high"
    if any(pattern.search(text) for pattern in MID_PATTERNS):
        return "mid"
    return None


def _overlaps(left: str, right: str) -> bool:
    normalized_left = re.sub(r"\s+", "", left)
    normalized_right = re.sub(r"\s+", "", right)
    return normalized_left in normalized_right or normalized_right in normalized_left


def _split_clauses(text: str) -> list[str]:
    return [
        clause.strip(" ,")
        for clause in re.split(r"[.!?\n]+|\s+(?:그리고|또한)\s+", text)
        if clause.strip(" ,")
    ]


def enforce_safety_policy(
    request_text: str,
    assessment: SafetyAssessment,
) -> SafetyPolicyDecision:
    """Apply deterministic safety floors after the model's structured classification."""

    normalized: list[SafetyFinding] = []
    for finding in assessment.findings:
        rule_classification = _rule_classification(finding.source_text)
        classification = finding.classification
        if rule_classification and RISK_ORDER[rule_classification] > RISK_ORDER[classification]:
            classification = rule_classification
        normalized.append(finding.model_copy(update={"classification": classification}))

    guard_index = 1
    for clause in _split_clauses(request_text):
        classification = _rule_classification(clause)
        if classification is None:
            continue
        if any(_overlaps(clause, finding.source_text) for finding in normalized):
            continue
        normalized.append(
            SafetyFinding(
                finding_id=f"guard-{guard_index}",
                source_text=clause,
                classification=classification,
                category="deterministic_safety_rule",
                reason="명시적 안전 규칙에 따라 위험도를 상향했어요.",
            )
        )
        guard_index += 1

    blocking_texts = [
        finding.source_text
        for finding in normalized
        if finding.classification in {"high", "emergency"}
    ]
    normalized = [
        finding
        for finding in normalized
        if finding.classification in {"high", "emergency"}
        or not any(_overlaps(finding.source_text, text) for text in blocking_texts)
    ]

    deduplicated: list[SafetyFinding] = []
    seen: set[tuple[str, SafetyClassification]] = set()
    for finding in normalized:
        key = (re.sub(r"\s+", " ", finding.source_text).strip(), finding.classification)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(finding)

    allowed = tuple(
        finding for finding in deduplicated if finding.classification in {"low", "mid"}
    )
    high = tuple(finding for finding in deduplicated if finding.classification == "high")
    excluded = tuple(
        finding for finding in deduplicated if finding.classification == "not_actionable"
    )
    emergency = tuple(
        finding for finding in deduplicated if finding.classification == "emergency"
    )
    highest = max(
        (finding.classification for finding in deduplicated),
        key=RISK_ORDER.__getitem__,
        default="not_actionable",
    )

    return SafetyPolicyDecision(
        assessment=assessment.model_copy(update={"findings": deduplicated}),
        allowed_findings=allowed,
        high_findings=high,
        excluded_findings=excluded,
        emergency_findings=emergency,
        summary=SafetySummary(
            highest_classification=highest,
            emergency_blocked=bool(emergency),
            high_discarded_count=len(high),
            not_actionable_count=len(excluded),
            mid_confirmation_count=sum(
                finding.classification == "mid" for finding in allowed
            ),
        ),
    )
