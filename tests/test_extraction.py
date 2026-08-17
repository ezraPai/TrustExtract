from pipeline.extraction import extract_fields
from pipeline.ocr import OCRLine


def line(text: str, y: float) -> OCRLine:
    return OCRLine(
        text=text,
        confidence=0.9,
        bbox=((10.0, y), (200.0, y), (200.0, y + 20), (10.0, y + 20)),
    )


def test_extracts_four_receipt_fields_from_ocr_lines():
    lines = [
        line("99 SPEED MART S/B (519537-X)", 100),
        line("LOT P.T. 2811, JALAN ANGSA", 130),
        line("TAMAN BERKELEY 41150 KLANG, SELANGOR", 160),
        line("21-05-17", 220),
        line("Total Sales (inclusive SST)", 400),
        line("20.90", 430),
        line("CASH RM", 460),
        line("21.00", 490),
    ]

    fields = extract_fields(lines)

    assert fields["company"].value == "99 SPEED MART S/B (519537-X)"
    assert fields["address"].value == "LOT P.T. 2811, JALAN ANGSA TAMAN BERKELEY 41150 KLANG, SELANGOR"
    assert fields["date"].value == "21-05-17"
    assert fields["total"].value == "20.90"
    assert fields["total"].source_line_indices == (5,)


def test_returns_blank_when_the_required_evidence_is_absent():
    fields = extract_fields([line("WELCOME", 100), line("Thank you", 200)])

    assert fields["date"].value is None
    assert fields["total"].value is None


def test_total_payable_beats_a_total_in_the_tax_summary():
    lines = [
        line("Total Amt Payable:", 500),
        line("159.00", 500),
        line("GST Summary", 650),
        line("Total", 700),
        line("9.00", 700),
    ]

    assert extract_fields(lines)["total"].value == "159.00"
