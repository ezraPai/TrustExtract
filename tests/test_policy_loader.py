import json

from backend.app.policy_loader import load_field_policies


def test_loads_field_specific_calibrated_policy(tmp_path):
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "field_policies": {
                    "company": {"review_threshold": 0.6, "accept_threshold": 1.0},
                    "address": {"review_threshold": 0.6, "accept_threshold": 1.0},
                    "date": {"review_threshold": 0.6, "accept_threshold": 0.61},
                    "total": {"review_threshold": 0.6, "accept_threshold": 1.0},
                }
            }
        ),
        encoding="utf-8",
    )

    policies = load_field_policies(policy_path)

    assert policies["date"].accept_threshold == 0.61
    assert policies["address"].accept_threshold == 1.0
