import pytest

from pipeline.policy import Decision, ThresholdPolicy, apply_policy


def test_policy_has_three_operational_outcomes():
    policy = ThresholdPolicy(review_threshold=0.60, accept_threshold=0.85)

    accepted = apply_policy("20.50", 0.90, policy)
    reviewed = apply_policy("20.50", 0.70, policy)
    abstained = apply_policy("20.50", 0.40, policy)

    assert accepted.decision is Decision.ACCEPT
    assert accepted.automation_value == "20.50"
    assert accepted.review_candidate is None
    assert reviewed.decision is Decision.REVIEW
    assert reviewed.automation_value is None
    assert reviewed.review_candidate == "20.50"
    assert abstained.decision is Decision.ABSTAIN
    assert abstained.automation_value is None
    assert abstained.review_candidate is None


def test_policy_abstains_when_value_or_score_is_missing():
    policy = ThresholdPolicy()

    assert apply_policy(None, 0.99, policy).decision is Decision.ABSTAIN
    assert apply_policy("20.50", None, policy).decision is Decision.ABSTAIN


def test_policy_rejects_invalid_threshold_order():
    with pytest.raises(ValueError):
        ThresholdPolicy(review_threshold=0.85, accept_threshold=0.85)
