from fastapi.testclient import TestClient

import backend.app.main as api_main
from backend.app.database import store_processed_document


def test_review_api_lists_and_completes_pending_field(tmp_path, monkeypatch):
    database_path = tmp_path / "trustextract.db"
    monkeypatch.setattr(api_main, "DATABASE_PATH", database_path)
    monkeypatch.setattr(api_main, "UPLOADS_DIR", tmp_path / "uploads")

    with TestClient(api_main.app) as client:
        document = store_processed_document(
            database_path,
            original_filename="receipt.jpg",
            stored_path="uploads/receipt.jpg",
            ocr_line_count=5,
            fields=[
                {
                    "field_name": "total",
                    "candidate_value": "20.90",
                    "confidence_score": 0.71,
                    "ocr_quality": 0.71,
                    "format_validity": 1.0,
                    "context_evidence": 0.35,
                    "decision": "review",
                    "automation_value": None,
                    "review_candidate": "20.90",
                    "decision_reason": "confidence_between_review_0.60_and_accept_1.00",
                    "extraction_rule": "total_keyword_or_adjacent_monetary_value",
                }
            ],
        )

        queue = client.get("/reviews")
        assert queue.status_code == 200
        assert queue.json()[0]["document_id"] == document["id"]

        response = client.patch(
            f"/documents/{document['id']}/fields/total/review",
            json={"human_value": "20.80", "review_status": "corrected"},
        )
        assert response.status_code == 200
        assert response.json()["human_value"] == "20.80"
        assert client.get("/reviews").json() == []
