"""Calibration and evaluation utilities for selective field extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Iterable

from pipeline.dataset import TARGET_FIELDS
from pipeline.evaluation import field_is_correct, prediction_value
from pipeline.policy import Decision, ThresholdPolicy, apply_policy


@dataclass(frozen=True)
class SelectiveMetrics:
    """Quality and workload metrics for a three-way automation policy."""

    support: int
    accepted: int
    accepted_correct: int
    review: int
    abstain: int

    @property
    def coverage(self) -> float | None:
        return self.accepted / self.support if self.support else None

    @property
    def selective_accuracy(self) -> float | None:
        return self.accepted_correct / self.accepted if self.accepted else None

    @property
    def selective_risk(self) -> float | None:
        accuracy = self.selective_accuracy
        return 1.0 - accuracy if accuracy is not None else None

    @property
    def review_rate(self) -> float | None:
        return self.review / self.support if self.support else None

    @property
    def abstention_rate(self) -> float | None:
        return self.abstain / self.support if self.support else None

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            **asdict(self),
            "coverage": self.coverage,
            "selective_accuracy": self.selective_accuracy,
            "selective_risk": self.selective_risk,
            "review_rate": self.review_rate,
            "abstention_rate": self.abstention_rate,
        }


def confidence_score(record: dict[str, Any], field: str) -> float | None:
    """Read and validate a Phase 4 confidence score from one prediction."""

    extraction = record.get("extractions", {}).get(field, {})
    confidence = extraction.get("confidence", {}) if isinstance(extraction, dict) else {}
    value = confidence.get("score") if isinstance(confidence, dict) else None
    if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
        return None
    return float(value)


def decision_for_field(record: dict[str, Any], field: str, policy: ThresholdPolicy):
    """Apply a policy to one field in a Phase 4 confidence record."""

    return apply_policy(prediction_value(record, field), confidence_score(record, field), policy)


def evaluate_field(
    records: Iterable[dict[str, Any]], field: str, policy: ThresholdPolicy
) -> SelectiveMetrics:
    """Evaluate a single field under a fixed policy using labelled examples."""

    support = accepted = accepted_correct = review = abstain = 0
    for record in records:
        correct = field_is_correct(record, field)
        if correct is None:
            continue
        support += 1
        decision = decision_for_field(record, field, policy).decision
        if decision is Decision.ACCEPT:
            accepted += 1
            accepted_correct += int(correct)
        elif decision is Decision.REVIEW:
            review += 1
        else:
            abstain += 1
    return SelectiveMetrics(
        support=support,
        accepted=accepted,
        accepted_correct=accepted_correct,
        review=review,
        abstain=abstain,
    )


def evaluate_policy(records: Iterable[dict[str, Any]], policy: ThresholdPolicy) -> dict[str, Any]:
    """Evaluate all fields under one global policy."""

    materialized = list(records)
    by_field = {field: evaluate_field(materialized, field, policy) for field in TARGET_FIELDS}
    overall = SelectiveMetrics(
        support=sum(metrics.support for metrics in by_field.values()),
        accepted=sum(metrics.accepted for metrics in by_field.values()),
        accepted_correct=sum(metrics.accepted_correct for metrics in by_field.values()),
        review=sum(metrics.review for metrics in by_field.values()),
        abstain=sum(metrics.abstain for metrics in by_field.values()),
    )
    return {
        "policy": policy.to_dict(),
        "field_metrics": {field: metrics.to_dict() for field, metrics in by_field.items()},
        "overall": overall.to_dict(),
    }


def evaluate_field_policies(
    records: Iterable[dict[str, Any]], policies: dict[str, ThresholdPolicy]
) -> dict[str, Any]:
    """Evaluate field-specific policies, allowing unsafe fields to be withheld."""

    if set(policies) != set(TARGET_FIELDS):
        raise ValueError("A field-specific policy must provide all SROIE target fields")
    materialized = list(records)
    by_field = {
        field: evaluate_field(materialized, field, policies[field])
        for field in TARGET_FIELDS
    }
    overall = SelectiveMetrics(
        support=sum(metrics.support for metrics in by_field.values()),
        accepted=sum(metrics.accepted for metrics in by_field.values()),
        accepted_correct=sum(metrics.accepted_correct for metrics in by_field.values()),
        review=sum(metrics.review for metrics in by_field.values()),
        abstain=sum(metrics.abstain for metrics in by_field.values()),
    )
    return {
        "field_policies": {field: policies[field].to_dict() for field in TARGET_FIELDS},
        "field_metrics": {field: metrics.to_dict() for field, metrics in by_field.items()},
        "overall": overall.to_dict(),
    }


def threshold_grid(start: float, stop: float, step: float) -> list[float]:
    """Build a stable inclusive decimal threshold grid without float drift."""

    if not 0.0 <= start <= 1.0 or not 0.0 <= stop <= 1.0 or start > stop:
        raise ValueError("Threshold range must satisfy 0 <= start <= stop <= 1")
    if step <= 0:
        raise ValueError("Threshold step must be positive")

    current = Decimal(str(start))
    upper = Decimal(str(stop))
    increment = Decimal(str(step))
    values: list[float] = []
    while current <= upper:
        values.append(float(current))
        current += increment
    return values


def build_coverage_accuracy_curve(
    records: Iterable[dict[str, Any]],
    *,
    review_threshold: float,
    thresholds: Iterable[float],
) -> list[dict[str, Any]]:
    """Evaluate automation coverage/accuracy at candidate accept thresholds."""

    materialized = list(records)
    curve: list[dict[str, Any]] = []
    for accept_threshold in thresholds:
        if accept_threshold <= review_threshold:
            continue
        policy = ThresholdPolicy(review_threshold=review_threshold, accept_threshold=accept_threshold)
        evaluation = evaluate_policy(materialized, policy)
        curve.append({"accept_threshold": accept_threshold, **evaluation["overall"]})
    return curve


def build_field_coverage_accuracy_curve(
    records: Iterable[dict[str, Any]],
    *,
    field: str,
    review_threshold: float,
    thresholds: Iterable[float],
) -> list[dict[str, Any]]:
    """Build a threshold curve for one field rather than mixing field types."""

    materialized = list(records)
    curve: list[dict[str, Any]] = []
    for accept_threshold in thresholds:
        if accept_threshold <= review_threshold:
            continue
        policy = ThresholdPolicy(review_threshold=review_threshold, accept_threshold=accept_threshold)
        metrics = evaluate_field(materialized, field, policy)
        curve.append({"accept_threshold": accept_threshold, **metrics.to_dict()})
    return curve


def select_threshold(
    curve: list[dict[str, Any]], *, target_selective_accuracy: float, min_accepted: int
) -> dict[str, Any]:
    """Choose maximum coverage that meets a target selective accuracy.

    If the confidence score cannot meet the target with enough accepted values,
    return the best observed reliable point and explicitly mark that fallback.
    """

    if not 0.0 <= target_selective_accuracy <= 1.0:
        raise ValueError("target_selective_accuracy must be between 0 and 1")
    if min_accepted < 1:
        raise ValueError("min_accepted must be at least 1")

    usable = [row for row in curve if row["accepted"] >= min_accepted and row["selective_accuracy"] is not None]
    if not usable:
        raise ValueError("No threshold accepts the requested minimum number of labelled fields")

    qualifying = [row for row in usable if row["selective_accuracy"] >= target_selective_accuracy]
    if qualifying:
        chosen = max(qualifying, key=lambda row: (row["coverage"], -row["accept_threshold"]))
        return {"target_met": True, "fallback_used": False, "selected": chosen}

    chosen = max(
        usable,
        key=lambda row: (row["selective_accuracy"], row["coverage"], -row["accept_threshold"]),
    )
    return {"target_met": False, "fallback_used": True, "selected": chosen}
