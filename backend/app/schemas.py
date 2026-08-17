"""API response schemas for TrustExtract."""

from __future__ import annotations

from pydantic import BaseModel


class ExtractionResponse(BaseModel):
    id: int
    field_name: str
    candidate_value: str | None
    confidence_score: float
    ocr_quality: float
    format_validity: float
    context_evidence: float
    decision: str
    automation_value: str | None
    review_candidate: str | None
    decision_reason: str
    extraction_rule: str
    review_status: str
    human_value: str | None
    reviewed_at: str | None


class DocumentResponse(BaseModel):
    id: int
    original_filename: str
    status: str
    ocr_line_count: int
    created_at: str
    fields: list[ExtractionResponse]


class MetricsResponse(BaseModel):
    document_count: int
    decisions: dict[str, int]


class ReviewRequest(BaseModel):
    human_value: str
    review_status: str


class ReviewQueueItem(ExtractionResponse):
    document_id: int
    original_filename: str
    created_at: str
