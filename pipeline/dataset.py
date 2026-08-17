"""SROIE dataset discovery, validation, and deterministic splitting.

The public SROIE mirrors use slightly different directory names. This module
avoids hard-coding one mirror while refusing to use OCR box files as labels:
an annotation is only accepted when it contains at least one of the four
target entity keys.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import random
from typing import Any, Iterable


TARGET_FIELDS = ("company", "address", "date", "total")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
ANNOTATION_DIR_NAMES = {"entities", "entity", "annotations", "annotation", "labels", "label"}


@dataclass(frozen=True)
class ReceiptSample:
    """One receipt image together with its labelled target fields."""

    receipt_id: str
    image_path: str
    annotation_path: str
    fields: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalise_field_name(name: str) -> str | None:
    """Map common label spelling variants to the four SROIE target fields."""

    compact = "".join(character for character in name.lower() if character.isalnum())
    aliases = {
        "company": "company",
        "companyname": "company",
        "address": "address",
        "date": "date",
        "total": "total",
        "totalamount": "total",
        "amount": "total",
    }
    return aliases.get(compact)


def _stringify(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_stringify(part) for part in value if _stringify(part))
    if value is None:
        return ""
    return str(value).strip()


def read_annotation(path: Path) -> dict[str, str] | None:
    """Read a JSON entity annotation, returning only recognised non-empty fields.

    Some SROIE distributions use a `.txt` suffix despite JSON content, hence
    parsing is based on content rather than the file extension.
    """

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    fields: dict[str, str] = {}
    for raw_name, raw_value in payload.items():
        if not isinstance(raw_name, str):
            continue
        field_name = normalise_field_name(raw_name)
        value = _stringify(raw_value)
        if field_name and value:
            fields[field_name] = value

    return fields or None


def _iter_image_paths(images_dir: Path) -> Iterable[Path]:
    return (path for path in images_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)


def _annotation_index(annotations_dir: Path) -> dict[str, Path]:
    """Index files that are actual structured field annotations by file stem."""

    index: dict[str, Path] = {}
    for path in annotations_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".txt"}:
            continue
        if read_annotation(path) is not None:
            index.setdefault(path.stem, path)
    return index


def find_annotation_directories(data_dir: Path) -> list[Path]:
    """Find likely entity-label folders in a dataset tree."""

    return [
        path
        for path in data_dir.rglob("*")
        if path.is_dir() and path.name.lower() in ANNOTATION_DIR_NAMES
    ]


def find_image_directories(data_dir: Path) -> list[Path]:
    """Find directories containing images without assuming a mirror layout."""

    candidates: list[Path] = []
    for path in [data_dir, *[entry for entry in data_dir.rglob("*") if entry.is_dir()]]:
        if any(_iter_image_paths(path)):
            candidates.append(path)
    # Only retain leaf image directories. It prevents the dataset root from
    # duplicating every image found in nested train/test folders.
    return [
        path for path in candidates
        if not any(other != path and other.is_relative_to(path) for other in candidates)
    ]


def load_samples(images_dir: Path, annotations_dir: Path) -> tuple[list[ReceiptSample], list[str]]:
    """Create pairs using matching image/annotation stems.

    Returns a human-readable diagnostics list so that a bad dataset download is
    caught before OCR development begins.
    """

    images_dir = images_dir.resolve()
    annotations_dir = annotations_dir.resolve()
    annotation_by_stem = _annotation_index(annotations_dir)
    samples: list[ReceiptSample] = []
    diagnostics: list[str] = []

    for image_path in sorted(_iter_image_paths(images_dir)):
        annotation_path = annotation_by_stem.get(image_path.stem)
        if annotation_path is None:
            diagnostics.append(f"No structured annotation found for: {image_path.name}")
            continue
        fields = read_annotation(annotation_path)
        if fields is None:
            diagnostics.append(f"Unreadable annotation: {annotation_path.name}")
            continue
        samples.append(
            ReceiptSample(
                receipt_id=image_path.stem,
                image_path=str(image_path),
                annotation_path=str(annotation_path),
                fields=fields,
            )
        )

    if not samples:
        diagnostics.append(
            "No labelled image pairs were found. Check the two directories or use explicit --images-dir and --annotations-dir options."
        )
    return samples, diagnostics


def discover_samples(data_dir: Path) -> tuple[list[ReceiptSample], list[str]]:
    """Find the image/annotation directory pair with the most valid samples."""

    data_dir = data_dir.resolve()
    if not data_dir.exists():
        return [], [f"Dataset directory does not exist: {data_dir}"]

    image_dirs = find_image_directories(data_dir)
    annotation_dirs = find_annotation_directories(data_dir)
    if not image_dirs:
        return [], [f"No image directories found below: {data_dir}"]
    if not annotation_dirs:
        return [], [f"No entity annotation directories found below: {data_dir}"]

    best_samples: list[ReceiptSample] = []
    best_diagnostics: list[str] = []
    for images_dir in image_dirs:
        for annotations_dir in annotation_dirs:
            samples, diagnostics = load_samples(images_dir, annotations_dir)
            if len(samples) > len(best_samples):
                best_samples = samples
                best_diagnostics = diagnostics

    return best_samples, best_diagnostics


def split_samples(
    samples: list[ReceiptSample],
    *,
    seed: int = 42,
    development_ratio: float = 0.60,
    calibration_ratio: float = 0.20,
) -> dict[str, list[ReceiptSample]]:
    """Return a reproducible development/calibration/test split.

    The development split is for rule design, calibration for confidence and
    thresholds, and test is reserved for the final reported result.
    """

    if not 0 < development_ratio < 1:
        raise ValueError("development_ratio must be between 0 and 1")
    if not 0 < calibration_ratio < 1:
        raise ValueError("calibration_ratio must be between 0 and 1")
    if development_ratio + calibration_ratio >= 1:
        raise ValueError("development_ratio + calibration_ratio must be less than 1")
    if len(samples) < 5:
        raise ValueError("At least five labelled samples are needed to create the three splits")

    shuffled = list(samples)
    random.Random(seed).shuffle(shuffled)
    development_end = max(1, int(len(shuffled) * development_ratio))
    calibration_end = max(development_end + 1, int(len(shuffled) * (development_ratio + calibration_ratio)))
    calibration_end = min(calibration_end, len(shuffled) - 1)

    return {
        "development": shuffled[:development_end],
        "calibration": shuffled[development_end:calibration_end],
        "test": shuffled[calibration_end:],
    }


def write_splits(splits: dict[str, list[ReceiptSample]], output_path: Path, *, seed: int) -> None:
    """Persist the exact split so experiments remain reproducible."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seed": seed,
        "target_fields": list(TARGET_FIELDS),
        "splits": {name: [sample.to_dict() for sample in samples] for name, samples in splits.items()},
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

