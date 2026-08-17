"""FastAPI backend for confidence-aware receipt extraction."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.app.config import DATABASE_PATH, OCR_CACHE_DIR, POLICY_FILE, UPLOADS_DIR
from backend.app.database import (
    decision_summary,
    complete_review,
    document_count,
    get_document,
    get_document_storage_path,
    initialize_database,
    list_documents,
    review_queue,
    store_processed_document,
)
from backend.app.policy_loader import load_field_policies
from backend.app.schemas import DocumentResponse, ExtractionResponse, MetricsResponse, ReviewQueueItem, ReviewRequest
from backend.app.service import process_receipt
from pipeline.ocr import OCRUnavailableError


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database(DATABASE_PATH)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="TrustExtract API",
    version="0.1.0",
    description="Confidence-aware receipt extraction with selective automation.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def save_upload(upload: UploadFile) -> Path:
    filename = upload.filename or "receipt"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type. Use one of: {', '.join(sorted(SUPPORTED_SUFFIXES))}",
        )
    target = UPLOADS_DIR / f"{uuid4().hex}{suffix}"
    with target.open("wb") as destination:
        shutil.copyfileobj(upload.file, destination)
    return target


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(file: UploadFile = File(...)) -> dict:
    """Upload a receipt, process it, and persist every field-level decision."""

    saved_path = save_upload(file)
    try:
        policies = load_field_policies(POLICY_FILE)
        ocr_line_count, fields = process_receipt(saved_path, cache_dir=OCR_CACHE_DIR, policies=policies)
        return store_processed_document(
            DATABASE_PATH,
            original_filename=file.filename or saved_path.name,
            stored_path=str(saved_path),
            ocr_line_count=ocr_line_count,
            fields=fields,
        )
    except (FileNotFoundError, OCRUnavailableError, ValueError) as error:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except Exception:
        saved_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@app.get("/documents", response_model=list[DocumentResponse])
def documents(limit: int = 50) -> list[dict]:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="limit must be 1–100")
    return list_documents(DATABASE_PATH, limit=limit)


@app.get("/documents/{document_id}", response_model=DocumentResponse)
def document(document_id: int) -> dict:
    result = get_document(DATABASE_PATH, document_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return result


@app.get("/documents/{document_id}/image")
def document_image(document_id: int) -> FileResponse:
    """Serve only the image associated with the requested persisted document."""

    stored_path = get_document_storage_path(DATABASE_PATH, document_id)
    if stored_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    image_path = Path(stored_path)
    if not image_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored image not found")
    # Do not set a download filename: the endpoint is used both by the inline
    # preview and by the "Open full image" link in the review workspace.
    return FileResponse(image_path)


@app.get("/metrics", response_model=MetricsResponse)
def metrics() -> dict:
    return {
        "document_count": document_count(DATABASE_PATH),
        "decisions": decision_summary(DATABASE_PATH),
    }


@app.get("/reviews", response_model=list[ReviewQueueItem])
def reviews(limit: int = 50) -> list[dict]:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="limit must be 1–100")
    return review_queue(DATABASE_PATH, limit=limit)


@app.patch("/documents/{document_id}/fields/{field_name}/review", response_model=ExtractionResponse)
def review_field(document_id: int, field_name: str, body: ReviewRequest) -> dict:
    human_value = body.human_value.strip()
    if not human_value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="human_value cannot be blank")
    try:
        updated = complete_review(
            DATABASE_PATH,
            document_id=document_id,
            field_name=field_name,
            human_value=human_value,
            review_status=body.review_status,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Extraction field not found")
    return updated
