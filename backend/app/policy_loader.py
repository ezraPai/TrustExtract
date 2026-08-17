"""Load the calibration-selected field-specific acceptance policy."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.dataset import TARGET_FIELDS
from pipeline.policy import ThresholdPolicy


def load_field_policies(policy_path: Path) -> dict[str, ThresholdPolicy]:
    """Load Phase 6 policy JSON, including support for the older global shape."""

    if not policy_path.is_file():
        raise FileNotFoundError(
            f"Calibrated policy not found: {policy_path}. "
            "Restore config/calibrated_policy.json or set TRUSTEXTRACT_POLICY_FILE."
        )
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    if "field_policies" in payload:
        policies = {
            field: ThresholdPolicy(**policy_payload)
            for field, policy_payload in payload["field_policies"].items()
        }
        if set(policies) != set(TARGET_FIELDS):
            raise ValueError("Calibrated policy must include company, address, date, and total")
        return policies
    if "policy" in payload:
        policy = ThresholdPolicy(**payload["policy"])
        return {field: policy for field in TARGET_FIELDS}
    raise ValueError("Policy JSON does not contain policy or field_policies")
