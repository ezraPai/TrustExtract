from pipeline.policy import ThresholdPolicy
from pipeline.selective_evaluation import (
    build_field_coverage_accuracy_curve,
    evaluate_field_policies,
    build_coverage_accuracy_curve,
    evaluate_policy,
    select_threshold,
    threshold_grid,
)


def record(receipt_id: str, company: str, company_score: float) -> dict:
    return {
        "receipt_id": receipt_id,
        "ground_truth": {
            "company": company,
            "address": None,
            "date": None,
            "total": None,
        },
        "extractions": {
            "company": {"value": company, "confidence": {"score": company_score}},
            "address": {"value": None, "confidence": {"score": 0.0}},
            "date": {"value": None, "confidence": {"score": 0.0}},
            "total": {"value": None, "confidence": {"score": 0.0}},
        },
    }


def test_selective_metrics_count_only_accepted_values():
    records = [record("one", "ACME", 0.95), record("two", "BETA", 0.70)]
    # Make the reviewed candidate wrong; it must not affect selective accuracy.
    records[1]["extractions"]["company"]["value"] = "WRONG"

    report = evaluate_policy(records, ThresholdPolicy(review_threshold=0.60, accept_threshold=0.85))

    assert report["overall"]["coverage"] == 0.5
    assert report["overall"]["selective_accuracy"] == 1.0
    assert report["overall"]["review_rate"] == 0.5


def test_calibration_selects_highest_coverage_that_meets_target():
    records = [record("one", "ACME", 0.95), record("two", "BETA", 0.75), record("three", "GAMMA", 0.65)]
    records[1]["extractions"]["company"]["value"] = "WRONG"
    curve = build_coverage_accuracy_curve(
        records,
        review_threshold=0.60,
        thresholds=threshold_grid(0.61, 0.96, 0.10),
    )

    selected = select_threshold(curve, target_selective_accuracy=1.0, min_accepted=1)

    assert selected["target_met"] is True
    assert selected["selected"]["accept_threshold"] == 0.81
    assert selected["selected"]["coverage"] == 1 / 3


def test_field_specific_policy_can_withhold_an_unsafe_field():
    records = [record("one", "ACME", 0.95)]
    policies = {
        "company": ThresholdPolicy(review_threshold=0.60, accept_threshold=0.90),
        "address": ThresholdPolicy(review_threshold=0.60, accept_threshold=1.00),
        "date": ThresholdPolicy(review_threshold=0.60, accept_threshold=1.00),
        "total": ThresholdPolicy(review_threshold=0.60, accept_threshold=1.00),
    }

    report = evaluate_field_policies(records, policies)

    assert report["overall"]["accepted"] == 1
    assert report["field_metrics"]["company"]["coverage"] == 1.0


def test_field_curve_has_metrics_for_one_field():
    curve = build_field_coverage_accuracy_curve(
        [record("one", "ACME", 0.95)],
        field="company",
        review_threshold=0.60,
        thresholds=[0.90],
    )

    assert curve[0]["accepted"] == 1
