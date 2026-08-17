"""Selective-automation policy for confidence-aware field extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class Decision(StrEnum):
    """How a downstream workflow should handle one extracted field."""

    ACCEPT = "accept"
    REVIEW = "review"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class ThresholdPolicy:
    """Two thresholds define the automatic, review, and abstention regions."""

    review_threshold: float = 0.60
    accept_threshold: float = 0.85

    def __post_init__(self) -> None:
        for name, value in (("review_threshold", self.review_threshold), ("accept_threshold", self.accept_threshold)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.review_threshold >= self.accept_threshold:
            raise ValueError("review_threshold must be lower than accept_threshold")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyResult:
    """Decision result with fields safe for an automated downstream system."""

    decision: Decision
    automation_value: str | None
    review_candidate: str | None
    reason: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "decision": self.decision.value,
            "automation_value": self.automation_value,
            "review_candidate": self.review_candidate,
            "reason": self.reason,
        }


def apply_policy(value: str | None, confidence_score: float | None, policy: ThresholdPolicy) -> PolicyResult:
    """Convert one proposed field value into an operational workflow decision.

    - Accept: a value is safe to send to automation.
    - Review: retain the candidate for a human, but send no automated value.
    - Abstain: send no value and ask the human to enter it from the receipt.
    """

    if value is None or confidence_score is None:
        return PolicyResult(
            decision=Decision.ABSTAIN,
            automation_value=None,
            review_candidate=None,
            reason="no_extracted_value_or_confidence",
        )
    if not 0.0 <= confidence_score <= 1.0:
        return PolicyResult(
            decision=Decision.ABSTAIN,
            automation_value=None,
            review_candidate=None,
            reason="invalid_confidence_score",
        )
    if confidence_score >= policy.accept_threshold:
        return PolicyResult(
            decision=Decision.ACCEPT,
            automation_value=value,
            review_candidate=None,
            reason=f"confidence_at_or_above_accept_threshold_{policy.accept_threshold:.2f}",
        )
    if confidence_score >= policy.review_threshold:
        return PolicyResult(
            decision=Decision.REVIEW,
            automation_value=None,
            review_candidate=value,
            reason=f"confidence_between_review_{policy.review_threshold:.2f}_and_accept_{policy.accept_threshold:.2f}",
        )
    return PolicyResult(
        decision=Decision.ABSTAIN,
        automation_value=None,
        review_candidate=None,
        reason=f"confidence_below_review_threshold_{policy.review_threshold:.2f}",
    )

