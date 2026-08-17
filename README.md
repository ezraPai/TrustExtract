# TrustExtract

TrustExtract is a confidence-aware receipt extraction demo built around the
SROIE dataset. It extracts `company`, `address`, `date`, and `total`, then
decides whether to **accept**, send a value for **human review**, or
**abstain**.

## Environment setup

On Windows PowerShell, create and populate the project environment with:

```powershell
.\scripts\setup_env.ps1
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks local scripts, run the first command without changing
your machine-wide policy:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1
```

The script creates `.venv` and installs the project, KaggleHub, and test
dependencies. Use the environment's interpreter for all project commands:

```powershell
.\.venv\Scripts\python.exe scripts\inspect_dataset.py --download-kaggle --show 5
```

## Phase 1: dataset setup

The quickest setup uses KaggleHub. It downloads the dataset once into its
managed local cache (not into this repository), then the inspector discovers
the image/annotation layout automatically:

```powershell
.\.venv\Scripts\python.exe scripts\inspect_dataset.py --download-kaggle --show 5
```

On its first run KaggleHub may ask you to authenticate with Kaggle, depending
on your local Kaggle configuration. The dataset identifier is
`urbikn/sroie-datasetv2`.

Alternatively, place a labelled SROIE dataset beneath `data/sroie/`. The
loader supports the common layouts below:

```text
data/sroie/
  train/
    img/                  # or images/
    entities/             # or annotations/, labels/, or entity/
```

Each annotation must be JSON (either a `.json` file or JSON stored in a
`.txt` file) with these fields:

```json
{
  "company": "ACME STORE",
  "address": "12 Example Street",
  "date": "2025-01-31",
  "total": "18.50"
}
```

Run the inspector after copying the dataset:

```powershell
.\.venv\Scripts\python.exe scripts\inspect_dataset.py --data-dir data/sroie --show 5
```

It discovers valid image/annotation pairs, prints representative ground truth,
and writes a deterministic development/calibration/test split to
`artifacts/dataset_splits.json`.

For a different folder arrangement, explicitly provide the two directories:

```powershell
.\.venv\Scripts\python.exe scripts\inspect_dataset.py `
  --images-dir data/sroie/train/img `
  --annotations-dir data/sroie/train/entities
```

The dataset itself is intentionally ignored by Git. KaggleHub still needs a
local cache while the code runs, but you do not need to download, unzip, or
commit it manually.

## Phase 2: OCR and baseline extraction

Phase 2 uses RapidOCR to produce recognised receipt lines, bounding boxes,
and OCR confidence. Its transparent rules extract four fields and record the
source lines and rule used for each prediction.

Run five development receipts first:

```powershell
.\.venv\Scripts\python.exe scripts\run_extraction.py --split development --limit 5
```

This writes OCR caches to `artifacts/ocr/` and predictions to
`artifacts/phase2_development_predictions.json`. Re-running the same command
uses the cache, so it is fast while you improve the extraction rules.

Once the output looks sensible, run the complete development split:

```powershell
.\.venv\Scripts\python.exe scripts\run_extraction.py --split development
```

## Phase 3: baseline evaluation

Evaluate the saved development predictions with field-aware normalization:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_baseline.py
```

The report in `artifacts/phase3_baseline_metrics.json` includes per-field and
overall exact normalized-match accuracy, coverage, and representative errors.
Use the development split to improve rules. Keep the calibration and test
splits untouched for threshold selection and final reporting.

## Phase 4: confidence scoring

Attach an explainable reliability score to every extracted field:

```powershell
.\.venv\Scripts\python.exe scripts\score_confidence.py
```

The output in `artifacts/phase4_development_confidence.json` contains the
combined score and its components: OCR quality, format validity, and
receipt-layout/context evidence. This is intentionally a heuristic score—not
a calibrated probability. Phase 5–6 will select policy thresholds using the
calibration split and evaluate selective accuracy on the test split.

## Phase 5: Accept / Review / Abstain policy

Apply the initial three-way workflow policy to the development confidence
scores:

```powershell
.\.venv\Scripts\python.exe scripts\apply_policy.py
```

The initial operating policy is deliberately provisional:

```text
confidence >= 0.85  → ACCEPT: provide automation_value
0.60 to < 0.85      → REVIEW: provide review_candidate only
confidence < 0.60   → ABSTAIN: provide neither value
```

The output in `artifacts/phase5_development_decisions.json` keeps the raw
candidate and evidence for auditability, but only an accepted prediction is
available in `automation_value`. Phase 6 will choose the final thresholds on
the calibration split, not this development output.

## Phase 6: calibration and selective evaluation

Phase 6 selects the automation threshold from the **calibration** split, then
uses the **test** split exactly once for final coverage and selective-accuracy
reporting. Do not choose thresholds from test results.

Create calibration predictions and confidence scores:

```powershell
.\.venv\Scripts\python.exe scripts\run_extraction.py --split calibration --output artifacts/phase2_calibration_predictions.json
.\.venv\Scripts\python.exe scripts\score_confidence.py --predictions artifacts/phase2_calibration_predictions.json --output artifacts/phase4_calibration_confidence.json
```

Choose safe field-specific accept thresholds. A field is only automated if it
reaches the target 80% selective accuracy on calibration data with at least 15
accepted labelled fields. Otherwise, automatic acceptance is disabled for that
field and values are routed to review or abstention:

```powershell
.\.venv\Scripts\python.exe scripts\calibrate_thresholds.py
```

This creates `artifacts/phase6_calibrated_policy.json`, including a separate
coverage-versus-selective-accuracy curve per field and a clear flag for every
field that could not meet the 80% target.

Then create test predictions/confidence and evaluate the already-fixed policy:

```powershell
.\.venv\Scripts\python.exe scripts\run_extraction.py --split test --output artifacts/phase2_test_predictions.json
.\.venv\Scripts\python.exe scripts\score_confidence.py --predictions artifacts/phase2_test_predictions.json --output artifacts/phase4_test_confidence.json
.\.venv\Scripts\python.exe scripts\evaluate_selective.py
```

The final test metrics are in `artifacts/phase6_test_selective_metrics.json`;
the corresponding workflow decisions are in
`artifacts/phase6_test_decisions.json`.

### Calibration chart for slides

Install the optional plotting dependency once, then create PNG and SVG copies
of the calibration-only coverage-versus-selective-accuracy chart:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[plots]"
.\.venv\Scripts\python.exe scripts\plot_calibration_curve.py
```

The chart highlights the selected date threshold and clearly states which
fields were withheld because they did not reach the calibration target.
