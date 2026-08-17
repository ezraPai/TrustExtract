"""OCR adapter and on-disk cache for receipt text extraction.

RapidOCR is intentionally isolated in this module.  The extraction and later
confidence code consume the vendor-neutral ``OCRLine`` object, so changing the
OCR engine does not require rewriting the decision logic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class OCRLine:
    """A recognised text line, its quadrilateral bounding box, and OCR score."""

    text: str
    confidence: float
    bbox: tuple[tuple[float, float], ...]

    @property
    def top(self) -> float:
        return min(point[1] for point in self.bbox)

    @property
    def left(self) -> float:
        return min(point[0] for point in self.bbox)

    @property
    def height(self) -> float:
        return max(point[1] for point in self.bbox) - self.top

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OCRLine":
        return cls(
            text=str(payload["text"]),
            confidence=float(payload["confidence"]),
            bbox=tuple(tuple(float(coordinate) for coordinate in point) for point in payload["bbox"]),
        )


class OCRUnavailableError(RuntimeError):
    """Raised with an actionable message when the OCR engine is unavailable."""


@lru_cache(maxsize=1)
def _reader() -> Any:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as error:
        raise OCRUnavailableError(
            "RapidOCR is not installed. Activate .venv and run `pip install -e .`."
        ) from error
    return RapidOCR()


def _as_bbox(points: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
    if len(points) < 4:
        raise ValueError("OCR bounding box must contain four points")
    return tuple((float(point[0]), float(point[1])) for point in points)


def run_ocr(image_path: str | Path) -> list[OCRLine]:
    """Run OCR on one receipt and return geometrically ordered text lines."""

    path = Path(image_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Receipt image does not exist: {path}")

    result, _timings = _reader()(str(path))
    if not result:
        return []

    lines: list[OCRLine] = []
    for row in result:
        if len(row) < 3:
            continue
        bbox, text, confidence = row[0], str(row[1]).strip(), row[2]
        if not text:
            continue
        lines.append(OCRLine(text=text, confidence=float(confidence), bbox=_as_bbox(bbox)))

    # Receipt OCR is normally returned in reading order. Sorting makes that
    # assumption explicit and makes cached output reproducible.
    return sorted(lines, key=lambda line: (line.top, line.left))


def cache_path_for(image_path: str | Path, cache_dir: str | Path) -> Path:
    """Return a stable JSON cache filename for a receipt image."""

    return Path(cache_dir) / f"{Path(image_path).stem}.json"


def load_or_run_ocr(
    image_path: str | Path,
    *,
    cache_dir: str | Path = "artifacts/ocr",
    force: bool = False,
) -> list[OCRLine]:
    """Reuse cached OCR unless the source image changed or ``force`` is set."""

    source_path = Path(image_path).resolve()
    output_path = cache_path_for(source_path, cache_dir)
    source_mtime_ns = source_path.stat().st_mtime_ns

    if not force and output_path.is_file():
        try:
            cached = json.loads(output_path.read_text(encoding="utf-8"))
            if (
                cached.get("source_image") == str(source_path)
                and cached.get("source_mtime_ns") == source_mtime_ns
            ):
                return [OCRLine.from_dict(line) for line in cached["lines"]]
        except (OSError, ValueError, KeyError, TypeError):
            # A corrupted cache should never block an extraction run.
            pass

    lines = run_ocr(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "engine": "rapidocr-onnxruntime",
        "source_image": str(source_path),
        "source_mtime_ns": source_mtime_ns,
        "lines": [line.to_dict() for line in lines],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return lines
