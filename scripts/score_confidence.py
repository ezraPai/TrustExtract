"""Attach Phase 4 confidence evidence to Phase 2 extraction predictions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.confidence import score_extractions  # noqa: E402
from pipeline.extraction import FieldExtraction  # noqa: E402
from pipeline.ocr import OCRLine, cache_path_for  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("artifacts/phase2_development_predictions.json"),
        help="Phase 2 prediction JSON",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("artifacts/ocr"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase4_development_confidence.json"))
    return parser.parse_args()


def extraction_from_dict(field: str, payload: dict[str, object]) -> FieldExtraction:
    value = payload.get("value")
    return FieldExtraction(
        field=field,
        value=value if isinstance(value, str) else None,
        source_line_indices=tuple(int(index) for index in payload.get("source_line_indices", [])),
        rule=str(payload.get("rule", "unknown")),
    )


def read_cached_lines(image_path: str, cache_dir: Path) -> list[OCRLine]:
    path = cache_path_for(image_path, cache_dir)
    if not path.is_file():
        raise FileNotFoundError(f"OCR cache does not exist: {path}. Run scripts/run_extraction.py first.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [OCRLine.from_dict(line) for line in payload["lines"]]


def main() -> int:
    args = parse_args()
    if not args.predictions.is_file():
        print(f"Prediction file does not exist: {args.predictions}", file=sys.stderr)
        return 2

    payload = json.loads(args.predictions.read_text(encoding="utf-8"))
    enriched: list[dict[str, object]] = []
    for record in payload["predictions"]:
        try:
            lines = read_cached_lines(record["image_path"], args.cache_dir)
        except FileNotFoundError as error:
            print(error, file=sys.stderr)
            return 1
        extractions = {
            field: extraction_from_dict(field, extraction)
            for field, extraction in record["extractions"].items()
        }
        confidences = score_extractions(extractions, lines)
        updated_extractions = {
            field: {**extraction, "confidence": confidences[field].to_dict()}
            for field, extraction in record["extractions"].items()
        }
        enriched.append({**record, "extractions": updated_extractions})
        compact = {field: confidence.score for field, confidence in confidences.items()}
        print(f"[{record['receipt_id']}] confidence={compact}")

    output = {
        "score_type": "heuristic_reliability_score_not_calibrated_probability",
        "source_prediction_file": str(args.predictions),
        "receipt_count": len(enriched),
        "predictions": enriched,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved confidence results to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

