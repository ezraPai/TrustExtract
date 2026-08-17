"""Field-aware normalization used only for fair extraction evaluation.

Predictions retain their original OCR text.  Normalization is applied only
when comparing a prediction with SROIE ground truth, so formatting differences
such as ``19/05/18`` vs ``19-05-2018`` do not count as extraction errors.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re


TEXT_FIELDS = {"company", "address"}


def normalize_text(value: str | None) -> str | None:
    """Compare textual fields case-insensitively and without layout punctuation."""

    if value is None:
        return None
    normalised = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    return normalised or None


def normalize_date(value: str | None) -> str | None:
    """Convert common SROIE date layouts to ISO ``YYYY-MM-DD`` when possible."""

    if value is None:
        return None
    candidate = str(value).strip().strip("()")
    patterns = (
        # Numeric day-first formats are most common in SROIE.
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%Y%m%d",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        # A small number of labels use US month-first notation.
        "%m/%d/%Y", "%m-%d-%Y",
        # Month-name labels occur in the SROIE annotations as well.
        "%d %b %Y", "%d %b %y", "%d-%b-%Y", "%d-%b-%y", "%d/%b/%Y", "%d/%b/%y",
        "%b %d, %Y", "%b %d, %y",
    )
    for pattern in patterns:
        try:
            return datetime.strptime(candidate, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_total(value: str | None) -> str | None:
    """Convert currency text to a two-decimal string, retaining only valid money."""

    if value is None:
        return None
    candidate = re.sub(r"[^0-9,.-]", "", str(value))
    if not candidate:
        return None

    # ``1,234.56`` uses comma grouping; ``20,50`` uses a decimal comma.
    if candidate.count(",") == 1 and "." not in candidate:
        left, right = candidate.split(",")
        candidate = f"{left}.{right}" if len(right) == 2 else f"{left}{right}"
    else:
        candidate = candidate.replace(",", "")
    try:
        amount = Decimal(candidate)
    except InvalidOperation:
        return None
    if amount < 0:
        return None
    return f"{amount:.2f}"


def normalize_for_field(field: str, value: str | None) -> str | None:
    """Normalize one of the four supported SROIE field values."""

    if field in TEXT_FIELDS:
        return normalize_text(value)
    if field == "date":
        return normalize_date(value)
    if field == "total":
        return normalize_total(value)
    raise ValueError(f"Unsupported field: {field}")
