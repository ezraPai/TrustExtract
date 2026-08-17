import json

from pipeline.dataset import load_samples, read_annotation, split_samples
from pipeline.kaggle import SROIE_DATASET_HANDLE


def test_sroie_kaggle_dataset_handle_is_stable():
    assert SROIE_DATASET_HANDLE == "urbikn/sroie-datasetv2"


def test_read_annotation_supports_common_keys(tmp_path):
    annotation = tmp_path / "receipt_01.txt"
    annotation.write_text(
        json.dumps(
            {
                "Company Name": "ACME Store",
                "Address": ["12 Example St", "Bangkok"],
                "Date": "17/08/2026",
                "Total Amount": "THB 18.50",
            }
        ),
        encoding="utf-8",
    )

    assert read_annotation(annotation) == {
        "company": "ACME Store",
        "address": "12 Example St Bangkok",
        "date": "17/08/2026",
        "total": "THB 18.50",
    }


def test_load_samples_ignores_non_json_box_file(tmp_path):
    images = tmp_path / "img"
    annotations = tmp_path / "entities"
    images.mkdir()
    annotations.mkdir()
    (images / "receipt_01.jpg").write_bytes(b"not-an-image-needed-for-pairing")
    (annotations / "receipt_01.txt").write_text('{"company": "ACME", "total": "10.00"}', encoding="utf-8")
    (annotations / "receipt_02.txt").write_text("1,2,3,4,hello", encoding="utf-8")

    samples, diagnostics = load_samples(images, annotations)

    assert len(samples) == 1
    assert samples[0].receipt_id == "receipt_01"
    assert samples[0].fields["total"] == "10.00"
    assert diagnostics == []


def test_split_samples_is_deterministic(tmp_path):
    images = tmp_path / "img"
    annotations = tmp_path / "entities"
    images.mkdir()
    annotations.mkdir()
    for number in range(10):
        stem = f"receipt_{number:02d}"
        (images / f"{stem}.jpg").write_bytes(b"image")
        (annotations / f"{stem}.json").write_text('{"company": "ACME"}', encoding="utf-8")

    samples, _ = load_samples(images, annotations)
    first = split_samples(samples, seed=7)
    second = split_samples(samples, seed=7)

    assert {name: [item.receipt_id for item in split] for name, split in first.items()} == {
        name: [item.receipt_id for item in split] for name, split in second.items()
    }
    assert sum(len(split) for split in first.values()) == 10
