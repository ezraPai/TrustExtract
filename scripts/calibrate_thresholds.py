"""Choose an automation threshold from calibration data and save the policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.selective_evaluation import (  # noqa: E402
    build_field_coverage_accuracy_curve,
    evaluate_field_policies,
    select_threshold,
    threshold_grid,
)
from pipeline.dataset import TARGET_FIELDS  # noqa: E402
from pipeline.policy import ThresholdPolicy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confidence-file",
        type=Path,
        default=Path("artifacts/phase4_calibration_confidence.json"),
        help="Phase 4 confidence output created from the calibration split",
    )
    parser.add_argument("--review-threshold", type=float, default=0.60)
    parser.add_argument("--threshold-start", type=float, default=0.61)
    parser.add_argument("--threshold-stop", type=float, default=0.99)
    parser.add_argument("--threshold-step", type=float, default=0.01)
    parser.add_argument("--target-selective-accuracy", type=float, default=0.80)
    parser.add_argument("--min-accepted", type=int, default=15)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase6_calibrated_policy.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confidence_file.is_file():
        print(f"Confidence file does not exist: {args.confidence_file}", file=sys.stderr)
        return 2
    try:
        thresholds = threshold_grid(args.threshold_start, args.threshold_stop, args.threshold_step)
        records = json.loads(args.confidence_file.read_text(encoding="utf-8"))["predictions"]
        field_curves = {
            field: build_field_coverage_accuracy_curve(
                records,
                field=field,
                review_threshold=args.review_threshold,
                thresholds=thresholds,
            )
            for field in TARGET_FIELDS
        }
        field_selection = {
            field: select_threshold(
                field_curves[field],
                target_selective_accuracy=args.target_selective_accuracy,
                min_accepted=args.min_accepted,
            )
            for field in TARGET_FIELDS
        }
    except (ValueError, KeyError) as error:
        print(error, file=sys.stderr)
        return 2

    # Safety-first fallback: when a field cannot meet the stated calibration
    # target, no candidate from that field is automatically accepted. It still
    # reaches review or abstention based on the review threshold.
    field_policies: dict[str, ThresholdPolicy] = {}
    for field, selection in field_selection.items():
        if selection["target_met"]:
            accept_threshold = selection["selected"]["accept_threshold"]
        else:
            accept_threshold = 1.0
            selection["automatic_acceptance_disabled"] = True
        field_policies[field] = ThresholdPolicy(
            review_threshold=args.review_threshold,
            accept_threshold=accept_threshold,
        )

    output = {
        "selection_split": "calibration",
        "source_confidence_file": str(args.confidence_file),
        "target_selective_accuracy": args.target_selective_accuracy,
        "min_accepted": args.min_accepted,
        "selection_method": "field_specific_safety_first",
        "field_selection": field_selection,
        "field_policies": {field: policy.to_dict() for field, policy in field_policies.items()},
        "calibration_metrics_at_selected_policy": evaluate_field_policies(records, field_policies),
        "coverage_accuracy_curves_by_field": field_curves,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Calibration target: {args.target_selective_accuracy:.1%}")
    for field in TARGET_FIELDS:
        selection = field_selection[field]
        chosen = field_policies[field]
        if selection["target_met"]:
            selected = selection["selected"]
            print(
                f"{field:8} accept >= {chosen.accept_threshold:.2f}; "
                f"coverage={selected['coverage']:.1%}; accuracy={selected['selective_accuracy']:.1%}"
            )
        else:
            print(f"{field:8} automatic acceptance disabled: target not met on calibration")
    print(f"Saved calibrated policy to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
