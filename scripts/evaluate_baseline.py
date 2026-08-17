"""Evaluate Phase 2 predictions with field-aware normalized exact match."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.evaluation import evaluate_predictions  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("artifacts/phase2_development_predictions.json"),
        help="Output JSON produced by scripts/run_extraction.py",
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase3_baseline_metrics.json"))
    parser.add_argument("--error-limit", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.predictions.is_file():
        print(f"Prediction file does not exist: {args.predictions}", file=sys.stderr)
        return 2
    if args.error_limit < 0:
        print("--error-limit cannot be negative", file=sys.stderr)
        return 2

    payload = json.loads(args.predictions.read_text(encoding="utf-8"))
    report = evaluate_predictions(payload["predictions"], error_limit=args.error_limit)
    report["prediction_file"] = str(args.predictions)
    report["receipt_count"] = len(payload["predictions"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Receipts evaluated: {report['receipt_count']}")
    for field, metrics in report["field_metrics"].items():
        accuracy = metrics["accuracy"]
        label = f"{accuracy:.1%}" if accuracy is not None else "n/a"
        print(f"{field:8} accuracy={label:>6}  correct={metrics['correct']}/{metrics['support']}")
    overall = report["overall"]
    print(f"overall  accuracy={overall['accuracy']:.1%}  correct={overall['correct']}/{overall['support']}")
    print(f"Saved baseline metrics to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

