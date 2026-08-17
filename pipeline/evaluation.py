"""Baseline field-extraction metrics for TrustExtract."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from pipeline.dataset import TARGET_FIELDS
from pipeline.normalization import normalize_for_field


@dataclass(frozen=True)
class FieldMetrics:
    support: int
    predicted: int
    correct: int

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.support if self.support else None

    @property
    def coverage(self) -> float | None:
        return self.predicted / self.support if self.support else None

    def to_dict(self) -> dict[str, int | float | None]:
        return {**asdict(self), "accuracy": self.accuracy, "coverage": self.coverage}


def prediction_value(record: dict[str, Any], field: str) -> str | None:
    """Read a prediction from Phase 2 or Phase 4 result JSON."""

    extraction = record.get("extractions", {}).get(field, {})
    value = extraction.get("value") if isinstance(extraction, dict) else None
    return value if isinstance(value, str) else None


def field_is_correct(record: dict[str, Any], field: str) -> bool | None:
    """Return true/false for labelled ground truth, or None when it is missing."""

    ground_truth = record.get("ground_truth", {}).get(field)
    expected = normalize_for_field(field, ground_truth)
    if expected is None:
        return None
    actual = normalize_for_field(field, prediction_value(record, field))
    return actual == expected


def evaluate_predictions(records: Iterable[dict[str, Any]], *, error_limit: int = 5) -> dict[str, Any]:
    """Evaluate exact normalized-match accuracy per field and in aggregate."""

    metrics = {field: {"support": 0, "predicted": 0, "correct": 0} for field in TARGET_FIELDS}
    errors: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for record in records:
        receipt_id = record.get("receipt_id", "unknown")
        for field in TARGET_FIELDS:
            expected_raw = record.get("ground_truth", {}).get(field)
            expected = normalize_for_field(field, expected_raw)
            if expected is None:
                continue
            metrics[field]["support"] += 1
            predicted_raw = prediction_value(record, field)
            predicted = normalize_for_field(field, predicted_raw)
            if predicted is not None:
                metrics[field]["predicted"] += 1
            if predicted == expected:
                metrics[field]["correct"] += 1
            elif len(errors[field]) < error_limit:
                errors[field].append(
                    {
                        "receipt_id": receipt_id,
                        "ground_truth": expected_raw,
                        "prediction": predicted_raw,
                        "normalized_ground_truth": expected,
                        "normalized_prediction": predicted,
                    }
                )

    field_results = {field: FieldMetrics(**counts) for field, counts in metrics.items()}
    overall = FieldMetrics(
        support=sum(result.support for result in field_results.values()),
        predicted=sum(result.predicted for result in field_results.values()),
        correct=sum(result.correct for result in field_results.values()),
    )
    return {
        "field_metrics": {field: result.to_dict() for field, result in field_results.items()},
        "overall": overall.to_dict(),
        "error_examples": dict(errors),
    }

