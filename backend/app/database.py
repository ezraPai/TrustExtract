"""SQLite persistence for documents and field-level extraction decisions."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from typing import Any, Iterator


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(database_path)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    try:
        yield database
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def initialize_database(database_path: Path) -> None:
    """Create the schema if this is the first application startup."""

    with connection(database_path) as database:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                ocr_line_count INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'processed',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS extractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                candidate_value TEXT,
                confidence_score REAL NOT NULL,
                ocr_quality REAL NOT NULL,
                format_validity REAL NOT NULL,
                context_evidence REAL NOT NULL,
                decision TEXT NOT NULL,
                automation_value TEXT,
                review_candidate TEXT,
                decision_reason TEXT NOT NULL,
                extraction_rule TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'pending',
                human_value TEXT,
                reviewed_at TEXT,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
                UNIQUE(document_id, field_name)
            );

            CREATE INDEX IF NOT EXISTS index_extractions_document_id
                ON extractions(document_id);
            CREATE INDEX IF NOT EXISTS index_extractions_decision
                ON extractions(decision);

            UPDATE extractions
            SET review_status = 'not_required'
            WHERE decision = 'accept' AND review_status = 'pending';
            """
        )


def _document_from_rows(document: sqlite3.Row, fields: list[sqlite3.Row]) -> dict[str, Any]:
    return {
        "id": document["id"],
        "original_filename": document["original_filename"],
        "status": document["status"],
        "ocr_line_count": document["ocr_line_count"],
        "created_at": document["created_at"],
        "fields": [dict(field) for field in fields],
    }


def store_processed_document(
    database_path: Path,
    *,
    original_filename: str,
    stored_path: str,
    ocr_line_count: int,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist a processed document and all its extraction evidence atomically."""

    with connection(database_path) as database:
        cursor = database.execute(
            """
            INSERT INTO documents (original_filename, stored_path, ocr_line_count, status, created_at)
            VALUES (?, ?, ?, 'processed', ?)
            """,
            (original_filename, stored_path, ocr_line_count, _utc_now()),
        )
        document_id = int(cursor.lastrowid)
        for field in fields:
            database.execute(
                """
                INSERT INTO extractions (
                    document_id, field_name, candidate_value, confidence_score,
                    ocr_quality, format_validity, context_evidence, decision,
                    automation_value, review_candidate, decision_reason, extraction_rule, review_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    field["field_name"],
                    field["candidate_value"],
                    field["confidence_score"],
                    field["ocr_quality"],
                    field["format_validity"],
                    field["context_evidence"],
                    field["decision"],
                    field["automation_value"],
                    field["review_candidate"],
                    field["decision_reason"],
                    field["extraction_rule"],
                    field.get("review_status", "pending"),
                ),
            )
        document = database.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        extraction_rows = database.execute(
            "SELECT * FROM extractions WHERE document_id = ? ORDER BY id", (document_id,)
        ).fetchall()
    return _document_from_rows(document, extraction_rows)


def get_document(database_path: Path, document_id: int) -> dict[str, Any] | None:
    with connection(database_path) as database:
        document = database.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if document is None:
            return None
        fields = database.execute(
            "SELECT * FROM extractions WHERE document_id = ? ORDER BY id", (document_id,)
        ).fetchall()
    return _document_from_rows(document, fields)


def list_documents(database_path: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    with connection(database_path) as database:
        documents = database.execute(
            "SELECT * FROM documents ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        output: list[dict[str, Any]] = []
        for document in documents:
            fields = database.execute(
                "SELECT * FROM extractions WHERE document_id = ? ORDER BY id", (document["id"],)
            ).fetchall()
            output.append(_document_from_rows(document, fields))
    return output


def decision_summary(database_path: Path) -> dict[str, int]:
    with connection(database_path) as database:
        rows = database.execute(
            "SELECT decision, COUNT(*) AS count FROM extractions GROUP BY decision ORDER BY decision"
        ).fetchall()
    return {row["decision"]: row["count"] for row in rows}


def document_count(database_path: Path) -> int:
    with connection(database_path) as database:
        row = database.execute("SELECT COUNT(*) AS count FROM documents").fetchone()
    return int(row["count"])


def review_queue(database_path: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    """Return review and abstention fields that still need a human decision."""

    with connection(database_path) as database:
        rows = database.execute(
            """
            SELECT
                extractions.*,
                documents.original_filename,
                documents.created_at,
                documents.id AS document_id
            FROM extractions
            JOIN documents ON documents.id = extractions.document_id
            WHERE extractions.review_status = 'pending'
              AND extractions.decision IN ('review', 'abstain')
            ORDER BY documents.id DESC, extractions.id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def complete_review(
    database_path: Path,
    *,
    document_id: int,
    field_name: str,
    human_value: str,
    review_status: str,
) -> dict[str, Any] | None:
    """Persist a reviewer-approved or corrected value and return that field."""

    if review_status not in {"approved", "corrected"}:
        raise ValueError("review_status must be approved or corrected")
    with connection(database_path) as database:
        field = database.execute(
            """
            SELECT * FROM extractions
            WHERE document_id = ? AND field_name = ?
            """,
            (document_id, field_name),
        ).fetchone()
        if field is None:
            return None
        if field["decision"] not in {"review", "abstain"}:
            raise ValueError("Only review or abstain fields can be human-reviewed")
        database.execute(
            """
            UPDATE extractions
            SET human_value = ?, review_status = ?, reviewed_at = ?
            WHERE id = ?
            """,
            (human_value, review_status, _utc_now(), field["id"]),
        )
        updated = database.execute("SELECT * FROM extractions WHERE id = ?", (field["id"],)).fetchone()
    return dict(updated)
