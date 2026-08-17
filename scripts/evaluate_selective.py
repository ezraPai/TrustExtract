"""Apply a calibrated policy once to test confidence results and report metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.dataset import TARGET_FIELDS  # noqa: E402
from pipeline.policy import ThresholdPolicy  # noqa: E402
from pipeline.selective_evaluation import decision_for_field, evaluate_field_policies, evaluate_policy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confidence-file",
        type=Path,
        default=Path("artifacts/phase4_test_confidence.json"),
        help="Phase 4 confidence output created from the held-out test split",
    )
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=Path("artifacts/phase6_calibrated_policy.json"),
        help="Calibration-selected policy JSON",
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase6_test_selective_metrics.json"))
    parser.add_argument("--decisions-output", type=Path, default=Path("artifacts/phase6_test_decisions.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confidence_file.is_file() or not args.policy_file.is_file():
        print("Both --confidence-file and --policy-file must exist.", file=sys.stderr)
        return 2

    confidence_payload = json.loads(args.confidence_file.read_text(encoding="utf-8"))
    policy_payload = json.loads(args.policy_file.read_text(encoding="utf-8"))
    try:
        if "field_policies" in policy_payload:
            field_policies = {
                field: ThresholdPolicy(**payload)
                for field, payload in policy_payload["field_policies"].items()
            }
            policy = None
        else:
            field_policies = None
            policy = ThresholdPolicy(**policy_payload["policy"])
    except (KeyError, TypeError, ValueError) as error:
        print(f"Invalid policy file: {error}", file=sys.stderr)
        return 2

    records = confidence_payload["predictions"]
    metrics = evaluate_field_policies(records, field_policies) if field_policies else evaluate_policy(records, policy)
    metrics_output = {
        "evaluation_split": "test",
        "source_confidence_file": str(args.confidence_file),
        "source_policy_file": str(args.policy_file),
        "receipt_count": len(records),
        **metrics,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metrics_output, indent=2, ensure_ascii=False), encoding="utf-8")

    decisions: list[dict[str, object]] = []
    for record in records:
        extractions = {
            field: {
                **record["extractions"][field],
                "policy": decision_for_field(record, field, field_policies[field] if field_policies else policy).to_dict(),
            }
            for field in TARGET_FIELDS
        }
        decisions.append({**record, "extractions": extractions})
    args.decisions_output.parent.mkdir(parents=True, exist_ok=True)
    args.decisions_output.write_text(
        json.dumps(
            {
                "evaluation_split": "test",
                "policy": policy.to_dict() if policy else None,
                "field_policies": {field: item.to_dict() for field, item in field_policies.items()} if field_policies else None,
                "receipt_count": len(decisions),
                "predictions": decisions,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    overall = metrics["overall"]
    accuracy = overall["selective_accuracy"]
    accuracy_label = f"{accuracy:.1%}" if accuracy is not None else "n/a"
    print(f"Held-out test receipts: {len(records)}")
    print(f"Coverage: {overall['coverage']:.1%}")
    print(f"Selective accuracy: {accuracy_label}")
    print(f"Review rate: {overall['review_rate']:.1%}; abstention rate: {overall['abstention_rate']:.1%}")
    print(f"Saved test metrics to: {args.output}")
    print(f"Saved test decisions to: {args.decisions_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
