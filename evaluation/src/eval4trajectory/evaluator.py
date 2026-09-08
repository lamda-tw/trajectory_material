from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

from .catalog import INDICATORS, TOTAL_MAX_SCORE, IndicatorDefinition, SignalPattern
from .models import (
    GateFailure,
    IndicatorResult,
    IndicatorStatus,
    TrajectoryEvidence,
    TrajectoryMessage,
    TrajectoryReport,
)
from .parser import parse_trajectory


_COMPLETION = re.compile(
    r"\b(?:done|fixed|completed|deployed|published|all checks pass(?:ed)?)\b|"
    r"已(?:完成|修复|部署|发布)|部署完成|修复完成|全部.*通过",
    re.IGNORECASE,
)
_ROOT_CAUSE = re.compile(
    r"root cause|found (?:it|the issue)|problem confirmed|问题找到了|根因|问题确认|问题定位",
    re.IGNORECASE,
)
_ANCHOR_VERIFY = re.compile(
    r"expected|now correctly|fix is verified|before.*after|验证结果|修复后|正确显示|结果.*正确",
    re.IGNORECASE | re.DOTALL,
)
_FULL_REGRESSION = re.compile(
    r"all .*checks.*pass|verification.*pass|regression|0\s+errors|全部.*(?:校验|检查).*通过|回归",
    re.IGNORECASE | re.DOTALL,
)
_DELIVERY_STATE = re.compile(
    r"local only|not deployed|server|deployed|published|run[_ -]?id|仅本地|未部署|服务器|上线",
    re.IGNORECASE,
)


def _round(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _role_matches(role: str, expected: tuple[str, ...]) -> bool:
    normalized = role.strip().lower()
    return any(normalized == item.lower() for item in expected)


def _matches(message: TrajectoryMessage, signal: SignalPattern) -> bool:
    return _role_matches(message.role, signal.roles) and bool(
        re.search(signal.regex, message.text, re.IGNORECASE | re.DOTALL)
    )


def _previous_assistant(
    messages: tuple[TrajectoryMessage, ...], position: int
) -> TrajectoryMessage | None:
    for message in reversed(messages[:position]):
        if _role_matches(message.role, ("AI", "assistant")):
            return message
    return None


def _next_assistant(
    messages: tuple[TrajectoryMessage, ...], position: int
) -> TrajectoryMessage | None:
    for message in messages[position + 1 :]:
        if _role_matches(message.role, ("AI", "assistant")):
            return message
    return None


def _incidents(
    definition: IndicatorDefinition,
    messages: tuple[TrajectoryMessage, ...],
) -> list[tuple[TrajectoryMessage, tuple[str, ...]]]:
    raw: list[tuple[TrajectoryMessage, str]] = []
    for message in messages:
        for signal in definition.failure_patterns:
            if _matches(message, signal):
                raw.append((message, signal.label))
    if not raw:
        return []

    grouped: list[list[tuple[TrajectoryMessage, str]]] = []
    for match in raw:
        if grouped and match[0].index - grouped[-1][-1][0].index <= 1:
            grouped[-1].append(match)
        else:
            grouped.append([match])

    incidents: list[tuple[TrajectoryMessage, tuple[str, ...]]] = []
    for group in grouped:
        primary = next(
            (item[0] for item in group if _role_matches(item[0].role, ("用户", "user"))),
            group[0][0],
        )
        incidents.append((primary, tuple(dict.fromkeys(item[1] for item in group))))
    # User correction is the strongest trajectory evidence.  Once a definition
    # has at least one user-backed incident, assistant-only debugging notes are
    # treated as corroboration, not additional failures.  This avoids counting
    # transient statements such as "the DU is missing from my search output".
    user_backed = [
        item
        for item in incidents
        if _role_matches(item[0].role, ("用户", "user"))
    ]
    return user_backed or incidents


def _pass_evidence(
    definition: IndicatorDefinition, messages: tuple[TrajectoryMessage, ...]
) -> list[TrajectoryMessage]:
    return [
        message
        for message in messages
        if any(_matches(message, signal) for signal in definition.pass_patterns)
    ]


def _build_evidence(
    definition: IndicatorDefinition,
    messages: tuple[TrajectoryMessage, ...],
    incidents: list[tuple[TrajectoryMessage, tuple[str, ...]]],
) -> tuple[TrajectoryEvidence, ...]:
    evidences: list[TrajectoryEvidence] = []
    seen_completion = False
    for incident, labels in incidents:
        position = incident.index - 1
        previous = _previous_assistant(messages, position)
        repair = _next_assistant(messages, position)
        recurrence = seen_completion
        if repair and _COMPLETION.search(repair.text):
            seen_completion = True
        evidences.append(
            TrajectoryEvidence(
                check_id=definition.check_id,
                failure_tag=definition.failure_tag,
                signal_labels=labels,
                message_index=incident.index,
                trajectory_time=incident.timestamp,
                role=incident.role,
                excerpt=incident.excerpt(),
                conclusion=definition.conclusion,
                expected=definition.expected,
                previous_completion_index=previous.index if previous else None,
                previous_completion_excerpt=previous.excerpt(220) if previous else "",
                repair_index=repair.index if repair else None,
                repair_excerpt=repair.excerpt(360) if repair else "",
                recurrence=recurrence,
            )
        )
    return tuple(evidences)


def _evaluate_signal_indicator(
    definition: IndicatorDefinition,
    messages: tuple[TrajectoryMessage, ...],
) -> IndicatorResult:
    incidents = _incidents(definition, messages)
    passes = _pass_evidence(definition, messages)
    evidence = _build_evidence(definition, messages, incidents)
    gates: tuple[GateFailure, ...] = ()
    if incidents:
        status = IndicatorStatus.FAILED
        score = 0.0
        summary = f"检测到 {len(incidents)} 个已成立的失败事件。"
        if definition.gate_id:
            first = incidents[0][0]
            gates = (
                GateFailure(
                    definition.gate_id,
                    definition.check_id,
                    definition.conclusion,
                    first.timestamp,
                ),
            )
    elif passes:
        status = IndicatorStatus.PASSED
        score = definition.max_score
        summary = f"未发现失败信号，检测到 {len(passes)} 条显式通过证据。"
    else:
        status = IndicatorStatus.NOT_OBSERVED
        score = 0.0
        summary = "轨迹中没有足够的失败或通过证据，不把未观察到误判为通过。"
    return IndicatorResult(
        check_id=definition.check_id,
        title=definition.title,
        dimension=definition.dimension,
        max_score=definition.max_score,
        score=score,
        status=status,
        summary=summary,
        failure_tag=definition.failure_tag,
        n=len(incidents) if incidents else (1 if passes else 0),
        e=len(incidents),
        metrics={
            "failure_events": len(incidents),
            "pass_evidence": len(passes),
            "recurrences": sum(item.recurrence for item in evidence),
        },
        evidence=evidence,
        gate_failures=gates,
    )


def _evaluate_recovery(
    messages: tuple[TrajectoryMessage, ...],
    upstream: tuple[IndicatorResult, ...],
) -> IndicatorResult:
    events = [item for result in upstream for item in result.evidence]
    if not events:
        return IndicatorResult(
            check_id="I3",
            title="负反馈修复闭环",
            dimension="interaction",
            max_score=4,
            score=0,
            status=IndicatorStatus.NOT_OBSERVED,
            summary="没有观察到可评价的纠错事件。",
            failure_tag="incomplete_recovery",
            n=0,
            e=0,
        )

    by_index = {message.index: message for message in messages}
    component_total = 0
    incomplete = 0
    for event in events:
        repair = by_index.get(event.repair_index or -1)
        if repair is None:
            incomplete += 1
            continue
        components = sum(
            bool(pattern.search(repair.text))
            for pattern in (_ROOT_CAUSE, _ANCHOR_VERIFY, _FULL_REGRESSION, _DELIVERY_STATE)
        )
        component_total += components
        if components < 4:
            incomplete += 1

    raw = 4.0 * component_total / (len(events) * 4)
    recurrence_count = sum(event.recurrence for event in events)
    if recurrence_count:
        raw = min(raw, 2.0)
    score = _round(raw)
    status = (
        IndicatorStatus.PASSED
        if score == 4
        else IndicatorStatus.PARTIAL
        if score > 0
        else IndicatorStatus.FAILED
    )
    recovery_evidence = tuple(
        TrajectoryEvidence(
            check_id="I3",
            failure_tag="incomplete_recovery",
            signal_labels=("纠错闭环不完整",),
            message_index=event.message_index,
            trajectory_time=event.trajectory_time,
            role=event.role,
            excerpt=event.excerpt,
            conclusion=(
                "同类问题在宣称修复后复发。"
                if event.recurrence
                else "修复回复未同时提供根因、锚点、全量回归和交付状态。"
            ),
            expected="根因、局部锚点、全量回归、交付/run 状态四项闭环。",
            previous_completion_index=event.previous_completion_index,
            previous_completion_excerpt=event.previous_completion_excerpt,
            repair_index=event.repair_index,
            repair_excerpt=event.repair_excerpt,
            recurrence=event.recurrence,
        )
        for event in events
        if event.recurrence
        or not (
            (repair := by_index.get(event.repair_index or -1))
            and all(
                pattern.search(repair.text)
                for pattern in (_ROOT_CAUSE, _ANCHOR_VERIFY, _FULL_REGRESSION, _DELIVERY_STATE)
            )
        )
    )
    return IndicatorResult(
        check_id="I3",
        title="负反馈修复闭环",
        dimension="interaction",
        max_score=4,
        score=score,
        status=status,
        summary=(
            f"纠错事件 {len(events)} 个，闭环组件完成 "
            f"{component_total}/{len(events) * 4}，复发 {recurrence_count} 个。"
        ),
        failure_tag="incomplete_recovery",
        n=len(events),
        e=incomplete,
        metrics={
            "events": len(events),
            "completed_components": component_total,
            "expected_components": len(events) * 4,
            "recurrences": recurrence_count,
        },
        evidence=recovery_evidence,
    )


class TrajectoryEvaluator:
    rubric_version = "56A09AQ-trajectory-v1.0-mvp12"

    def evaluate_messages(
        self,
        messages: Iterable[TrajectoryMessage],
        *,
        trajectory_file: str = "",
    ) -> TrajectoryReport:
        message_tuple = tuple(messages)
        if not message_tuple:
            raise ValueError("trajectory must contain at least one message")
        signal_results = tuple(
            _evaluate_signal_indicator(definition, message_tuple)
            for definition in INDICATORS
        )
        recovery = _evaluate_recovery(message_tuple, signal_results)
        results = signal_results + (recovery,)
        raw_score = _round(sum(item.score for item in results))
        evaluated = _round(
            sum(
                item.max_score
                for item in results
                if item.status is not IndicatorStatus.NOT_OBSERVED
            )
        )
        normalized = _round(100 * raw_score / evaluated) if evaluated else None
        coverage = _round(evaluated / TOTAL_MAX_SCORE)
        dimensions: dict[str, float] = defaultdict(float)
        dimension_max: dict[str, float] = defaultdict(float)
        for item in results:
            dimensions[item.dimension] += item.score
            dimension_max[item.dimension] += item.max_score
        gates = tuple(gate for item in results for gate in item.gate_failures)
        passed = bool(
            normalized is not None
            and normalized >= 75
            and coverage >= 0.8
            and not gates
        )
        return TrajectoryReport(
            schema_version="eval4trajectory.score-result.v1",
            rubric_version=self.rubric_version,
            trajectory_file=trajectory_file,
            raw_score=raw_score,
            max_score=TOTAL_MAX_SCORE,
            evaluated_max_score=evaluated,
            normalized_score=normalized,
            coverage=coverage,
            passed=passed,
            dimension_scores={key: _round(value) for key, value in dimensions.items()},
            dimension_max_scores={
                key: _round(value) for key, value in dimension_max.items()
            },
            results=results,
            gate_failures=gates,
            metadata={
                "message_count": len(message_tuple),
                "indicator_count": len(results),
                "scoring_note": (
                    "12项MVP原始满分为50；normalized_score仅按已观察项归一化。"
                ),
                "rule_source": "evaluation/src/eval4trajectory/catalog.py#INDICATORS",
            },
        )

    def evaluate(self, trajectory_path: str | Path) -> TrajectoryReport:
        path = Path(trajectory_path)
        return self.evaluate_messages(
            parse_trajectory(path), trajectory_file=str(path.resolve())
        )
