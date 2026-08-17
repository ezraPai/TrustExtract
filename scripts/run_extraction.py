"""Run the Phase 2 OCR and rule baseline against a saved dataset split."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.extraction import extract_fields  # noqa: E402
from pipeline.ocr import OCRUnavailableError, load_or_run_ocr  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "calibration", "test"), default="development")
    parser.add_argument("--splits-file", type=Path, default=Path("artifacts/dataset_splits.json"))
    parser.add_argument("--limit", type=int, help="Optional number of receipts to process")
    parser.add_argument("--cache-dir", type=Path, default=Path("artifacts/ocr"))
    parser.add_argument("--force-ocr", action="store_true", help="Ignore cached OCR and run the engine again")
    parser.add_argument("--output", type=Path, help="Prediction JSON location")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.splits_file.is_file():
        print(f"Split file does not exist: {args.splits_file}", file=sys.stderr)
        return 2

    payload = json.loads(args.splits_file.read_text(encoding="utf-8"))
    samples = payload["splits"][args.split]
    if args.limit is not None:
        if args.limit < 1:
            print("--limit must be at least 1", file=sys.stderr)
            return 2
        samples = samples[: args.limit]
    if not samples:
        print(f"No receipts in {args.split} split.", file=sys.stderr)
        return 1

    output_path = args.output or Path(f"artifacts/phase2_{args.split}_predictions.json")
    predictions: list[dict[str, object]] = []
    for position, sample in enumerate(samples, start=1):
        receipt_id = sample["receipt_id"]
        try:
            ocr_lines = load_or_run_ocr(
                sample["image_path"],
                cache_dir=args.cache_dir,
                force=args.force_ocr,
            )
        except (FileNotFoundError, OCRUnavailableError) as error:
            print(f"[{receipt_id}] {error}", file=sys.stderr)
            return 1

        fields = extract_fields(ocr_lines)
        field_values = {name: extraction.value for name, extraction in fields.items()}
        predictions.append(
            {
                "receipt_id": receipt_id,
                "image_path": sample["image_path"],
                "ground_truth": sample["fields"],
                "ocr_line_count": len(ocr_lines),
                "extractions": {name: extraction.to_dict() for name, extraction in fields.items()},
            }
        )
        print(f"[{position}/{len(samples)}] {receipt_id}: {field_values}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "split": args.split,
                "receipt_count": len(predictions),
                "predictions": predictions,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved Phase 2 predictions to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

