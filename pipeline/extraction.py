"""Transparent rule-based baseline extraction for SROIE receipt fields.

This is deliberately a baseline rather than a trained entity model.  Every
prediction records the rule and OCR lines it came from, which makes Phase 2
debuggable and supplies useful evidence for the confidence model in Phase 4.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable

from pipeline.ocr import OCRLine


DATE_PATTERN = re.compile(
    r"(?<!\d)(?:\d{4}[./-](?:0?[1-9]|1[0-2])[./-](?:0?[1-9]|[12]\d|3[01])|"
    r"(?:0?[1-9]|[12]\d|3[01])[./-](?:0?[1-9]|1[0-2])[./-](?:\d{2}|\d{4}))(?!\d)"
)
MONEY_PATTERN = re.compile(r"(?<![\d.,])(?:RM\s*)?(\d{1,3}(?:,\d{3})*|\d+)[.,](\d{2})(?!\d)", re.IGNORECASE)

TOTAL_KEYWORDS = ("grand total", "total sales", "total amount", "net total", "amount due", "total")
TOTAL_PENALTIES = ("subtotal", "sub total", "cash", "change", "tax", "rounding", "discount")
ADDRESS_KEYWORDS = (
    "jalan",
    "jln",
    "road",
    "lorong",
    "taman",
    "lot",
    "no.",
    "no ",
    "kampung",
    "bandar",
    "selangor",
    "malaysia",
    "kuala",
    "penang",
    "melaka",
    "pahang",
    "perak",
    "kedah",
    "johor",
    "sabah",
    "sarawak",
)
BUSINESS_KEYWORDS = ("sdn", "bhd", "s/b", "enterprise", "mart", "store", "restaurant", "trading")
NON_COMPANY_HEADER_KEYWORDS = ("checked", "original", "duplicate", "copy")


@dataclass(frozen=True)
class FieldExtraction:
    """One field prediction and the OCR evidence used to produce it."""

    field: str
    value: str | None
    source_line_indices: tuple[int, ...]
    rule: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "FieldExtraction":
        value = payload.get("value")
        return cls(
            field=str(payload["field"]),
            value=value if isinstance(value, str) else None,
            source_line_indices=tuple(int(index) for index in payload.get("source_line_indices", [])),
            rule=str(payload.get("rule", "unknown")),
        )


def _normalise_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    lowered = _normalise_text(text)
    return any(phrase in lowered for phrase in phrases)


def _looks_like_date(text: str) -> bool:
    return DATE_PATTERN.search(text) is not None


def _money_values(text: str) -> list[str]:
    """Return monetary strings while preserving the OCR text as evidence."""

    return [match.group(0).strip() for match in MONEY_PATTERN.finditer(text)]


def _looks_like_address(text: str) -> bool:
    lowered = _normalise_text(text)
    letters = sum(character.isalpha() for character in text)
    digits = sum(character.isdigit() for character in text)
    if _contains_any(lowered, BUSINESS_KEYWORDS):
        return False
    return (
        _contains_any(lowered, ADDRESS_KEYWORDS)
        or bool(re.search(r"\b\d{5}\b", text))
        or (letters >= 5 and digits > 0)
    )


def _is_gst_or_tax_metadata(text: str) -> bool:
    """Avoid matching the letter sequence ``gst`` inside a merchant name."""

    lowered = _normalise_text(text)
    return lowered.startswith("gst") or lowered.startswith("tax") or " gst " in lowered or " tax " in lowered


def _is_transaction_metadata(text: str) -> bool:
    lowered = _normalise_text(text)
    return _is_gst_or_tax_metadata(lowered) or any(
        word in lowered for word in ("invoice", "receipt", "telephone", "tel :", "cashier")
    )


def _select_company(lines: list[OCRLine]) -> FieldExtraction:
    best: tuple[float, int] | None = None
    for index, line in enumerate(lines[:8]):
        text = line.text
        lowered = _normalise_text(text)
        letters = sum(character.isalpha() for character in text)
        if letters < 3 or _looks_like_date(text) or _money_values(text):
            continue
        business_name = _contains_any(lowered, BUSINESS_KEYWORDS)
        if _contains_any(lowered, NON_COMPANY_HEADER_KEYWORDS) or _looks_like_address(text):
            continue
        if _is_transaction_metadata(text) and not business_name:
            continue

        score = 4.0 - (0.45 * index) + min(letters, 40) / 8
        if business_name:
            score += 2.0
        if len(text.split()) >= 2:
            score += 0.25
        if best is None or score > best[0]:
            best = (score, index)

    if best is None:
        return FieldExtraction("company", None, (), "no_header_company_candidate")
    index = best[1]
    return FieldExtraction("company", lines[index].text, (index,), "highest_scoring_header_line")


def _select_address(lines: list[OCRLine], company: FieldExtraction) -> FieldExtraction:
    if not company.source_line_indices:
        return FieldExtraction("address", None, (), "company_not_found")

    start = company.source_line_indices[0] + 1
    selected_indices: list[int] = []
    selected_text: list[str] = []
    # SROIE addresses normally appear directly below the merchant name.  Stop
    # at date/transaction metadata to avoid including purchased items.
    for index in range(start, min(start + 9, len(lines))):
        text = lines[index].text
        if _looks_like_date(text) or _money_values(text):
            break
        # GST/tax registration lines sometimes appear between the merchant
        # name and street address. Skip them, but do not end address search.
        if _is_gst_or_tax_metadata(text):
            continue
        if _contains_any(text, ("invoice", "receipt", "telephone", "tel :", "cashier")):
            break
        if not selected_text and not _looks_like_address(text):
            continue
        if selected_text and len(text) < 3:
            continue
        selected_indices.append(index)
        selected_text.append(text)
        if len(selected_text) == 4:
            break
        if re.search(r"\b\d{5}\b", text) and _contains_any(text, ("selangor", "malaysia", "pahang", "johor", "penang", "perak", "kedah")):
            break

    if not selected_text:
        return FieldExtraction("address", None, (), "no_address_below_company")
    return FieldExtraction(
        "address",
        " ".join(selected_text),
        tuple(selected_indices),
        "contiguous_header_lines_below_company",
    )


def _select_date(lines: list[OCRLine]) -> FieldExtraction:
    best: tuple[float, int, str] | None = None
    for index, line in enumerate(lines):
        match = DATE_PATTERN.search(line.text)
        if match is None:
            continue
        score = 1.0 + max(0.0, 1.5 - index * 0.03)
        if "date" in _normalise_text(line.text):
            score += 4.0
        if index > 0 and "date" in _normalise_text(lines[index - 1].text):
            score += 2.0
        candidate = (score, index, match.group(0))
        if best is None or candidate[0] > best[0]:
            best = candidate

    if best is None:
        return FieldExtraction("date", None, (), "no_valid_date_pattern")
    return FieldExtraction("date", best[2], (best[1],), "valid_date_pattern_with_context")


def _select_total(lines: list[OCRLine]) -> FieldExtraction:
    best: tuple[float, int, str] | None = None

    def label_strength(text: str) -> float:
        lowered = _normalise_text(text)
        if "subtotal" in lowered or "sub total" in lowered:
            return 0.0
        if "payable" in lowered or "amount due" in lowered:
            return 10.0
        if "total amt" in lowered or "total amount" in lowered:
            return 8.5
        if lowered == "total":
            return 8.0
        if "grand total" in lowered or "total amount" in lowered or "net total" in lowered:
            return 7.0
        if "total" in lowered:
            return 5.0
        return 0.0

    for index, line in enumerate(lines):
        for value in _money_values(line.text):
            score = 0.02 * index
            if _contains_any(line.text, TOTAL_KEYWORDS):
                score += 6.0
            if _contains_any(line.text, TOTAL_PENALTIES):
                score -= 6.0

            # Labels and values are often separate OCR boxes on the same
            # visual row. Use geometry instead of only adjacent list order.
            for label in lines:
                strength = label_strength(label.text)
                if strength == 0:
                    continue
                distance = abs(line.top - label.top)
                exact_row_tolerance = max(12.0, line.height, label.height) * 0.75
                near_row_tolerance = max(20.0, line.height, label.height) * 2.0
                if distance <= exact_row_tolerance:
                    score += strength
                elif distance <= near_row_tolerance:
                    score += strength * 0.2

            # Do not select a monetary value aligned with CASH, CHANGE, TAX,
            # or ROUNDING simply because it sits close to a TOTAL label.
            for penalty_label in lines:
                if not _contains_any(penalty_label.text, TOTAL_PENALTIES):
                    continue
                distance = abs(line.top - penalty_label.top)
                penalty_tolerance = max(12.0, line.height, penalty_label.height) * 0.75
                if distance <= penalty_tolerance:
                    score -= 8.0
            candidate = (score, index, value)
            if best is None or candidate[0] > best[0]:
                best = candidate

    if best is None:
        return FieldExtraction("total", None, (), "no_monetary_candidate")
    return FieldExtraction("total", best[2], (best[1],), "total_keyword_or_adjacent_monetary_value")


def extract_fields(lines: list[OCRLine]) -> dict[str, FieldExtraction]:
    """Extract the four SROIE fields using interpretable receipt-layout rules."""

    company = _select_company(lines)
    return {
        "company": company,
        "address": _select_address(lines, company),
        "date": _select_date(lines),
        "total": _select_total(lines),
    }
