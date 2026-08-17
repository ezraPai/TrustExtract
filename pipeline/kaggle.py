"""KaggleHub integration for obtaining the SROIE dataset."""

from __future__ import annotations

from pathlib import Path


SROIE_DATASET_HANDLE = "urbikn/sroie-datasetv2"


def download_sroie_dataset() -> Path:
    """Download/cache SROIE through KaggleHub and return its local cache path.

    KaggleHub owns the cache location. The dataset is therefore not copied into
    the Git repository and is reused automatically on later runs.
    """

    try:
        import kagglehub
    except ImportError as error:
        raise RuntimeError(
            "KaggleHub is not installed. Run `pip install -e .` or `pip install kagglehub`."
        ) from error

    return Path(kagglehub.dataset_download(SROIE_DATASET_HANDLE))

