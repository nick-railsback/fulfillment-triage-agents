"""Configurable thresholds for semantic validation checks.

All thresholds are tunable here without touching validator code.
"""

# Post-Intake: minimum extraction confidence before flagging
INTAKE_CONFIDENCE_FLOOR: float = 0.6

# Post-Scorer: maximum allowed divergence between deterministic score
# and LLM severity total before issuing a warning.
# Divergence = abs(deterministic_score_normalized - llm_severity_normalized)
# where both are normalized to 0-1 scale (det/60, llm/40).
SCORER_DIVERGENCE_THRESHOLD: float = 0.4

# Post-Scorer: expected score bounds by category [min, max]
# Tickets scoring outside these bounds trigger a warning.
CATEGORY_SCORE_BOUNDS: dict[str, tuple[int, int]] = {
    "tracking_inquiry": (0, 45),
    "general_inquiry": (0, 40),
    "inventory_question": (0, 40),
    "address_change": (0, 50),
    "return_request": (5, 65),
    "refund_request": (5, 70),
    "shipping_delay": (5, 75),
    "billing_dispute": (8, 85),
    "wrong_item": (10, 80),
    "damaged_item": (15, 100),
    "missing_item": (15, 100),
    "other": (0, 100),
}

# Post-Router: routing decisions that are never valid for a given risk tier.
# Maps risk_tier -> set of forbidden routing decisions.
FORBIDDEN_ROUTING: dict[str, set[str]] = {
    "critical": {"auto_resolve"},
    "high": {"auto_resolve"},
}
