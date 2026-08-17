# TrustExtract

TrustExtract is a confidence-aware receipt extraction system. It extracts four
receipt fields (`company`, `address`, `date`, and `total`) and decides, for
each field, whether to accept it automatically, send it for human review, or
abstain.

## How to run

### 1. Create the environment

From Windows PowerShell in the project root:

```powershell
.\scripts\setup_env.ps1
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks the setup script, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1
```

### 2. Prepare the dataset and calibrated policy

The project uses KaggleHub to obtain SROIE without manually copying the
dataset into the repository:

```powershell
python scripts\inspect_dataset.py --download-kaggle --show 5
```

To reproduce the calibrated policy from scratch, run:

```powershell
python scripts\run_extraction.py --split development
python scripts\score_confidence.py

python scripts\run_extraction.py --split calibration --output artifacts\phase2_calibration_predictions.json
python scripts\score_confidence.py --predictions artifacts\phase2_calibration_predictions.json --output artifacts\phase4_calibration_confidence.json
python scripts\calibrate_thresholds.py
```

This produces `artifacts/phase6_calibrated_policy.json`, which the backend
uses when processing uploaded receipts.

### 3. Start the application

Start the FastAPI backend in one terminal:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Start the separate frontend in a second terminal:

```powershell
python -m http.server 5173 --directory frontend
```

Open the application at:

```text
http://127.0.0.1:5173
```

The backend API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

Uploaded receipt images are stored in `data/uploads/`; extraction results and
human review corrections are stored in `data/trustextract.db`.

## What I chose and why

I chose **Option 1: Document Understanding with Confidence** using the
**SROIE receipt dataset**.

The goal is not simply to extract text from a receipt. The central question is
whether the system should trust an extracted value enough to automate it.

The pipeline is:

```text
Receipt image -> OCR -> field extraction -> confidence evidence
-> Accept / Review / Abstain -> SQLite -> human correction
```

SROIE is a focused extraction task with ground truth for company, address,
date, and total. It made it possible to spend the limited project time on
selective automation and trustworthy decision-making rather than training a
large document model from scratch.

Confidence is based on three explainable signals:

- OCR quality for the source text.
- Field-format validity, such as a valid date or monetary value.
- Context and layout evidence, such as a value aligned with a `TOTAL` label.

The acceptance policy is selected using calibration data. Fields that do not
meet the target reliability are routed to human review or abstention rather
than being silently automated.

## What already existed vs. what I built

### Reused components

- **SROIE**: public receipt images and field annotations.
- **KaggleHub**: dataset download and caching.
- **RapidOCR**: pretrained OCR engine that provides text, bounding boxes, and
  OCR confidence.
- **FastAPI, SQLite, and browser APIs**: application infrastructure.

### Built for this project

- Dataset inspection, labelled image/annotation pairing, and reproducible
  development, calibration, and test splits.
- Transparent rule-based extraction of company, address, date, and total.
- OCR caching, field-aware normalization, and baseline evaluation.
- Explainable field-level confidence scoring.
- Calibration-driven selective automation policy and held-out evaluation.
- Coverage-versus-selective-accuracy calibration plots.
- FastAPI endpoints for receipt upload, extraction, persistence, and metrics.
- SQLite schema for documents, field predictions, confidence evidence,
  decisions, and human corrections.
- Separate frontend for upload, extraction evidence, decision display, and a
  persisted human-review queue.
