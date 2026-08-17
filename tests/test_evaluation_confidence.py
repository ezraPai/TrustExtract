from pipeline.confidence import score_extractions
from pipeline.evaluation import evaluate_predictions
from pipeline.extraction import FieldExtraction
from pipeline.ocr import OCRLine


def line(text: str, y: float, confidence: float = 0.9) -> OCRLine:
    return OCRLine(
        text=text,
        confidence=confidence,
        bbox=((10.0, y), (200.0, y), (200.0, y + 20), (10.0, y + 20)),
    )


def test_evaluation_uses_field_aware_normalization():
    report = evaluate_predictions(
        [
            {
                "receipt_id": "one",
                "ground_truth": {
                    "company": "TF Value-Mart Sdn Bhd",
                    "address": "No. 1, Jalan Angsa",
                    "date": "19/05/2018",
                    "total": "20.50",
                },
                "extractions": {
                    "company": {"value": "TFValue-MartSdnBhd"},
                    "address": {"value": "No 1 Jalan Angsa"},
                    "date": {"value": "19-05-18"},
                    "total": {"value": "RM20,50"},
                },
            }
        ]
    )

    assert report["overall"]["accuracy"] == 1.0


def test_confidence_preserves_component_evidence():
    lines = [
        line("ACME MART SDN BHD", 100, 0.95),
        line("No. 1, Jalan Angsa 41150 Klang", 140, 0.85),
        line("Date: 19/05/18", 220, 0.9),
        line("TOTAL", 400, 0.9),
        line("20.50", 400, 0.8),
    ]
    extractions = {
        "company": FieldExtraction("company", lines[0].text, (0,), "test"),
        "address": FieldExtraction("address", lines[1].text, (1,), "test"),
        "date": FieldExtraction("date", "19/05/18", (2,), "test"),
        "total": FieldExtraction("total", "20.50", (4,), "test"),
    }

    results = score_extractions(extractions, lines)

    assert results["total"].format_validity == 1.0
    assert results["total"].context_evidence == 1.0
    assert results["total"].score > 0.85
