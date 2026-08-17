"""Apply the Phase 5 Accept / Review / Abstain policy to confidence results."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.policy import ThresholdPolicy, apply_policy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confidence-file",
        type=Path,
        default=Path("artifacts/phase4_development_confidence.json"),
        help="Phase 4 confidence JSON",
    )
    parser.add_argument("--review-threshold", type=float, default=0.60)
    parser.add_argument("--accept-threshold", type=float, default=0.85)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase5_development_decisions.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confidence_file.is_file():
        print(f"Confidence file does not exist: {args.confidence_file}", file=sys.stderr)
        return 2
    try:
        policy = ThresholdPolicy(
            review_threshold=args.review_threshold,
            accept_threshold=args.accept_threshold,
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2

    source = json.loads(args.confidence_file.read_text(encoding="utf-8"))
    decisions: list[dict[str, object]] = []
    total_counts: Counter[str] = Counter()
    field_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for record in source["predictions"]:
        updated_extractions: dict[str, dict[str, object]] = {}
        for field, extraction in record["extractions"].items():
            confidence = extraction.get("confidence", {})
            score = confidence.get("score") if isinstance(confidence, dict) else None
            value = extraction.get("value")
            result = apply_policy(
                value if isinstance(value, str) else None,
                float(score) if isinstance(score, (int, float)) else None,
                policy,
            )
            updated_extractions[field] = {**extraction, "policy": result.to_dict()}
            total_counts[result.decision.value] += 1
            field_counts[field][result.decision.value] += 1
        decisions.append({**record, "extractions": updated_extractions})

    output = {
        "policy": policy.to_dict(),
        "source_confidence_file": str(args.confidence_file),
        "receipt_count": len(decisions),
        "decision_summary": {
            "overall": dict(total_counts),
            "by_field": {field: dict(counts) for field, counts in field_counts.items()},
        },
        "predictions": decisions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Receipts processed: {len(decisions)}")
    print(f"Policy: accept >= {policy.accept_threshold:.2f}; review >= {policy.review_threshold:.2f}")
    for decision in ("accept", "review", "abstain"):
        print(f"{decision:8} {total_counts[decision]}")
    print(f"Saved Phase 5 decisions to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

