# TrustExtract

TrustExtract is a confidence-aware receipt extraction system. It extracts four
receipt fields (`company`, `address`, `date`, and `total`) and decides, for
each field, whether to accept it automatically, send it for human review, or
abstain.

## How to run

### Prerequisites

- Python 3.10 or newer.
- An internet connection the first time SROIE is downloaded through KaggleHub.
- Any modern browser. The application has been tested with Chrome/Edge; it is
  not tied to a specific operating system.

### 1. Create and activate the environment

All application code uses relative paths, `pathlib`, FastAPI, SQLite, and a
browser frontend, so it runs on Windows, macOS, and Linux. Only the shell
commands used to create and activate the virtual environment differ.

#### Windows (PowerShell)

```powershell
.\scripts\setup_env.ps1
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks the setup script, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1
```

#### macOS / Linux (bash or zsh)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The calibration-chart script additionally needs Matplotlib on any platform:

```bash
python -m pip install -e ".[plots]"
```

### 2. Prepare the dataset and calibrated policy

The project uses KaggleHub to obtain SROIE without manually copying the
dataset into the repository:

```text
python scripts/inspect_dataset.py --download-kaggle --show 5
```

To reproduce the calibrated policy from scratch, run:

```text
python scripts/run_extraction.py --split development
python scripts/score_confidence.py

python scripts/run_extraction.py --split calibration --output artifacts/phase2_calibration_predictions.json
python scripts/score_confidence.py --predictions artifacts/phase2_calibration_predictions.json --output artifacts/phase4_calibration_confidence.json
python scripts/calibrate_thresholds.py
```

This produces `artifacts/phase6_calibrated_policy.json`, which the backend
uses when processing uploaded receipts.

### 3. Start the application

Start the FastAPI backend in one activated terminal:

```text
python -m uvicorn backend.app.main:app --reload
```

Start the separate frontend in a second activated terminal:

```text
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

### Cross-platform reviewer note

After activation, use `python -m ...` commands rather than calling an
operating-system-specific executable directly. For example, do not depend on
the Windows-only path `.venv\Scripts\python.exe`; macOS and Linux use
`.venv/bin/python`. The README commands above deliberately avoid this
difference.

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


## Quantitative results

### Evaluation protocol

The 626 labelled SROIE receipts were split before policy selection into a
development set (375 receipts), a calibration set (125 receipts), and a
held-out test set (126 receipts). The raw extractor was measured on the
development set. Confidence thresholds were selected only on the calibration
set; the test set was used once for the final selective-automation evaluation.

Field accuracy below is a normalized exact match against the SROIE label. A
missing field counts as incorrect.

### Raw extraction baseline — development split

| Field | Labelled fields | Accuracy | Extraction coverage |
| --- | ---: | ---: | ---: |
| Company | 375 | 54.1% | 99.5% |
| Address | 375 | 17.9% | 98.1% |
| Date | 375 | 65.6% | 72.5% |
| Total | 373 | 56.8% | 99.7% |
| **Overall** | **1,498** | **48.6%** | **92.5%** |

This baseline demonstrates why returning every extraction automatically would
be unsafe, particularly for long addresses and OCR-sensitive amounts.

### Selective automation — held-out test split

The policy was calibrated with an 80% target selective accuracy and a minimum
of 15 accepted fields. Only the **date** field met this target at useful
volume, so its acceptance threshold is `0.61`. Automatic acceptance is
disabled for company, address, and total; they go to review or abstention.

| Outcome | Fields | Rate |
| --- | ---: | ---: |
| Automatically accepted | 80 | 15.9% |
| Correct among accepted | 71 / 80 | **88.8% selective accuracy** |
| Sent to human review | 378 | 75.1% |
| Abstained (left blank) | 45 | 8.9% |
| **Total labelled fields** | **503** | **100.0%** |

All 80 automatically accepted fields were dates. This corresponds to 63.5%
date coverage on the held-out test set, with 71 correct dates out of 80
accepted. The result illustrates the intended trade-off: the current system
automates less work, but the work it does automate is substantially more
reliable. The baseline and selective figures use different splits, so they
should not be treated as a direct like-for-like accuracy comparison.

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
