"""Explainable, field-level confidence scoring for Phase 4.

The resulting score is a heuristic reliability score, not a calibrated
probability. Phase 6 will use the calibration split to choose decision
thresholds and validate whether high scores are in fact more reliable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Mapping

from pipeline.extraction import FieldExtraction
from pipeline.normalization import normalize_for_field
from pipeline.ocr import OCRLine


@dataclass(frozen=True)
class ConfidenceAssessment:
    score: float
    ocr_quality: float
    format_validity: float
    context_evidence: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def _source_lines(extraction: FieldExtraction, lines: list[OCRLine]) -> list[OCRLine]:
    return [lines[index] for index in extraction.source_line_indices if 0 <= index < len(lines)]


def _document_height(lines: list[OCRLine]) -> float:
    return max((line.top + line.height for line in lines), default=1.0)


def _format_validity(field: str, value: str | None) -> float:
    if value is None:
        return 0.0
    if field == "date":
        return 1.0 if normalize_for_field("date", value) else 0.0
    if field == "total":
        return 1.0 if normalize_for_field("total", value) else 0.0
    if field == "company":
        letters = sum(character.isalpha() for character in value)
        return 1.0 if letters >= 5 else 0.45 if letters >= 3 else 0.0
    if field == "address":
        letters = sum(character.isalpha() for character in value)
        has_address_hint = bool(
            re.search(r"\b(?:jalan|jln|road|lorong|taman|lot|selangor|malaysia|\d{5})\b", value, re.IGNORECASE)
        )
        if letters < 8:
            return 0.0
        return 1.0 if has_address_hint else 0.65
    raise ValueError(f"Unsupported field: {field}")


def _total_context(source: list[OCRLine], lines: list[OCRLine]) -> float:
    if not source:
        return 0.0
    source_top = sum(line.top for line in source) / len(source)
    for line in lines:
        if "total" not in line.text.lower() or "subtotal" in line.text.lower():
            continue
        tolerance = max(12.0, line.height, source[0].height) * 0.75
        if abs(line.top - source_top) <= tolerance:
            return 1.0
    return 0.35


def _context_evidence(
    field: str,
    extraction: FieldExtraction,
    source: list[OCRLine],
    lines: list[OCRLine],
    all_extractions: Mapping[str, FieldExtraction],
) -> float:
    if not source:
        return 0.0
    document_height = _document_height(lines)
    source_top = min(line.top for line in source)
    position = source_top / document_height

    if field == "company":
        return 1.0 if position <= 0.25 else 0.6 if position <= 0.45 else 0.2
    if field == "address":
        company = all_extractions.get("company")
        if company and company.source_line_indices and extraction.source_line_indices:
            if min(extraction.source_line_indices) > max(company.source_line_indices):
                return 0.9
        return 0.45
    if field == "date":
        if any("date" in line.text.lower() for line in source):
            return 1.0
        return 0.75 if position <= 0.65 else 0.35
    if field == "total":
        return _total_context(source, lines)
    raise ValueError(f"Unsupported field: {field}")


def score_field(
    field: str,
    extraction: FieldExtraction,
    lines: list[OCRLine],
    all_extractions: Mapping[str, FieldExtraction],
) -> ConfidenceAssessment:
    """Combine OCR, field validity, and receipt-layout evidence into one score."""

    source = _source_lines(extraction, lines)
    ocr_quality = sum(line.confidence for line in source) / len(source) if source else 0.0
    format_validity = _format_validity(field, extraction.value)
    context_evidence = _context_evidence(field, extraction, source, lines, all_extractions)
    score = 0.50 * ocr_quality + 0.25 * format_validity + 0.25 * context_evidence
    return ConfidenceAssessment(
        score=round(max(0.0, min(1.0, score)), 4),
        ocr_quality=round(max(0.0, min(1.0, ocr_quality)), 4),
        format_validity=round(max(0.0, min(1.0, format_validity)), 4),
        context_evidence=round(max(0.0, min(1.0, context_evidence)), 4),
    )


def score_extractions(
    extractions: Mapping[str, FieldExtraction], lines: list[OCRLine]
) -> dict[str, ConfidenceAssessment]:
    """Score all four fields from a single receipt."""

    return {
        field: score_field(field, extraction, lines, extractions)
        for field, extraction in extractions.items()
    }

