"""Calibration tracking for confidence analysis and model drift detection."""

from typing import Literal

from pydantic import BaseModel


class CalibrationRecord(BaseModel):
    """Captures prediction vs. outcome for calibration analysis."""

    message_id: str

    # Scorer's prediction
    predicted_risk_tier: Literal["low", "medium", "high", "critical"]
    predicted_risk_score: int
    scorer_confidence: float | None = None

    # Router's final decision
    routing_decision: Literal["auto_resolve", "queue_for_review", "escalate"]
    overrides_applied: list[str] = []

    # Verifier's assessment
    verifier_verdict: Literal["pass", "fail", "needs_review"] | None = None
    verifier_confidence: float | None = None

    # Ground truth (from test expected values or human feedback)
    expected_category: str | None = None
    expected_risk_tier: str | None = None
    expected_routing: str | None = None
    actual_category: str | None = None

    # Derived
    category_correct: bool | None = None
    routing_correct: bool | None = None
    risk_tier_correct: bool | None = None
