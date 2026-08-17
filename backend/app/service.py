"""Orchestrate OCR, extraction, confidence, and calibrated selective policy."""

from __future__ import annotations

from pathlib import Path

from pipeline.confidence import score_extractions
from pipeline.dataset import TARGET_FIELDS
from pipeline.extraction import extract_fields
from pipeline.ocr import load_or_run_ocr
from pipeline.policy import ThresholdPolicy, apply_policy


def process_receipt(
    image_path: Path,
    *,
    cache_dir: Path,
    policies: dict[str, ThresholdPolicy],
) -> tuple[int, list[dict[str, object]]]:
    """Return persistence-ready field results for one uploaded receipt."""

    lines = load_or_run_ocr(image_path, cache_dir=cache_dir)
    extractions = extract_fields(lines)
    confidences = score_extractions(extractions, lines)
    fields: list[dict[str, object]] = []
    for field in TARGET_FIELDS:
        extraction = extractions[field]
        confidence = confidences[field]
        policy_result = apply_policy(extraction.value, confidence.score, policies[field])
        fields.append(
            {
                "field_name": field,
                "candidate_value": extraction.value,
                "confidence_score": confidence.score,
                "ocr_quality": confidence.ocr_quality,
                "format_validity": confidence.format_validity,
                "context_evidence": confidence.context_evidence,
                "decision": policy_result.decision.value,
                "automation_value": policy_result.automation_value,
                "review_candidate": policy_result.review_candidate,
                "decision_reason": policy_result.reason,
                "extraction_rule": extraction.rule,
                "review_status": "not_required" if policy_result.decision.value == "accept" else "pending",
            }
        )
    return len(lines), fields
