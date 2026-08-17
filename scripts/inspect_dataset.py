"""Validate SROIE image/annotation pairs and create reproducible data splits."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

# Allow `python scripts/inspect_dataset.py` without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.dataset import discover_samples, load_samples, split_samples, write_splits  # noqa: E402
from pipeline.kaggle import download_sroie_dataset  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="SROIE root directory; auto-discovers common layouts")
    parser.add_argument(
        "--download-kaggle",
        action="store_true",
        help="Download/cache urbikn/sroie-datasetv2 with KaggleHub, then inspect it",
    )
    parser.add_argument("--images-dir", type=Path, help="Explicit directory containing receipt images")
    parser.add_argument("--annotations-dir", type=Path, help="Explicit directory containing entity JSON annotations")
    parser.add_argument("--show", type=int, default=5, help="Number of representative samples to print")
    parser.add_argument("--seed", type=int, default=42, help="Random seed used for the saved split")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/dataset_splits.json"),
        help="Location for the reproducible split JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.download_kaggle and (args.data_dir is not None or args.images_dir is not None or args.annotations_dir is not None):
        print("Use --download-kaggle by itself; it supplies the dataset directory.", file=sys.stderr)
        return 2
    explicit_pair = args.images_dir is not None or args.annotations_dir is not None
    if explicit_pair and (args.images_dir is None or args.annotations_dir is None):
        print("Use both --images-dir and --annotations-dir together.", file=sys.stderr)
        return 2
    if not args.download_kaggle and not explicit_pair and args.data_dir is None:
        print("Provide --download-kaggle, --data-dir, or both --images-dir and --annotations-dir.", file=sys.stderr)
        return 2

    if args.download_kaggle:
        try:
            data_dir = download_sroie_dataset()
        except RuntimeError as error:
            print(error, file=sys.stderr)
            return 1
        print(f"KaggleHub dataset cache: {data_dir}")
        samples, diagnostics = discover_samples(data_dir)
    elif explicit_pair:
        samples, diagnostics = load_samples(args.images_dir, args.annotations_dir)
    else:
        samples, diagnostics = discover_samples(args.data_dir)

    print(f"Labelled receipt pairs: {len(samples)}")
    if not samples:
        for diagnostic in diagnostics[:10]:
            print(f"- {diagnostic}")
        return 1

    field_counts = Counter(field for sample in samples for field in sample.fields)
    print("Field coverage:")
    for field in ("company", "address", "date", "total"):
        print(f"  {field:8} {field_counts[field]}/{len(samples)}")

    print("\nRepresentative samples:")
    for sample in samples[: max(0, args.show)]:
        print(f"\n[{sample.receipt_id}]")
        print(f"  image: {sample.image_path}")
        for field in ("company", "address", "date", "total"):
            print(f"  {field:8}: {sample.fields.get(field, '<missing>')}")

    try:
        splits = split_samples(samples, seed=args.seed)
    except ValueError as error:
        print(f"\nSplit was not written: {error}", file=sys.stderr)
        return 1

    write_splits(splits, args.output, seed=args.seed)
    print("\nSaved reproducible split:")
    for name, split in splits.items():
        print(f"  {name:11} {len(split)}")
    print(f"  file        {args.output}")

    unmatched = sum(message.startswith("No structured annotation") for message in diagnostics)
    if unmatched:
        print(f"\nWarning: {unmatched} image(s) did not have a matching structured annotation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
