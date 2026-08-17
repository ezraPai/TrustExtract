from backend.app.database import complete_review, get_document, initialize_database, review_queue, store_processed_document


def test_sqlite_persists_document_and_field_decisions(tmp_path):
    database_path = tmp_path / "trustextract.db"
    initialize_database(database_path)

    created = store_processed_document(
        database_path,
        original_filename="receipt.png",
        stored_path="uploads/receipt.png",
        ocr_line_count=12,
        fields=[
            {
                "field_name": "date",
                "candidate_value": "19/05/18",
                "confidence_score": 0.91,
                "ocr_quality": 0.89,
                "format_validity": 1.0,
                "context_evidence": 0.75,
                "decision": "accept",
                "automation_value": "19/05/18",
                "review_candidate": None,
                "decision_reason": "confidence_at_or_above_accept_threshold_0.61",
                "extraction_rule": "valid_date_pattern_with_context",
            }
        ],
    )

    fetched = get_document(database_path, created["id"])

    assert fetched is not None
    assert fetched["original_filename"] == "receipt.png"
    assert fetched["fields"][0]["decision"] == "accept"
    assert fetched["fields"][0]["automation_value"] == "19/05/18"


def test_review_queue_and_human_correction_are_persisted(tmp_path):
    database_path = tmp_path / "trustextract.db"
    initialize_database(database_path)
    document = store_processed_document(
        database_path,
        original_filename="receipt.png",
        stored_path="uploads/receipt.png",
        ocr_line_count=8,
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

    assert len(review_queue(database_path)) == 1
    updated = complete_review(
        database_path,
        document_id=document["id"],
        field_name="total",
        human_value="20.80",
        review_status="corrected",
    )

    assert updated is not None
    assert updated["human_value"] == "20.80"
    assert updated["review_status"] == "corrected"
    assert review_queue(database_path) == []
