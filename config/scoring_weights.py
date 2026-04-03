"""Deterministic scoring factor tables for the Scorer Agent.

All weights are tunable here without touching agent code.
"""

# Issue category severity (0-15 points)
CATEGORY_SEVERITY: dict[str, int] = {
    "damaged_item": 15,
    "missing_item": 15,
    "wrong_item": 12,
    "shipping_delay": 8,
    "billing_dispute": 8,
    "refund_request": 6,
    "return_request": 5,
    "address_change": 3,
    "tracking_inquiry": 2,
    "inventory_question": 2,
    "general_inquiry": 1,
    "other": 1,
}

# Customer sentiment (0-15 points)
SENTIMENT_SCORES: dict[str, int] = {
    "angry": 15,
    "urgent": 12,
    "frustrated": 8,
    "neutral": 2,
    "positive": 0,
}

# Order value thresholds (0-10 points)
ORDER_VALUE_THRESHOLDS: list[tuple[float, int]] = [
    (500.0, 10),
    (200.0, 7),
    (100.0, 4),
]
ORDER_VALUE_DEFAULT: int = 1

# Customer tier (0-10 points)
TIER_SCORES: dict[str, int] = {
    "enterprise": 10,
    "vip": 7,
    "standard": 2,
}

# Repeat contact bonus (0-5 points)
REPEAT_CONTACT_BONUS: int = 5

# Multiple open tickets (0-5 points)
OPEN_TICKETS_HIGH: int = 5   # has_open_tickets >= 2
OPEN_TICKETS_LOW: int = 3    # has_open_tickets == 1


def compute_deterministic_score(
    issue_category: str,
    sentiment: str,
    order_value_usd: float | None,
    customer_tier: str,
    has_prior_contact: bool,
    has_open_tickets: int,
) -> int:
    """Compute the deterministic component of the risk score (0-60 max)."""
    score = 0

    score += CATEGORY_SEVERITY.get(issue_category, 1)
    score += SENTIMENT_SCORES.get(sentiment, 2)

    if order_value_usd is not None:
        value_points = ORDER_VALUE_DEFAULT
        for threshold, points in ORDER_VALUE_THRESHOLDS:
            if order_value_usd > threshold:
                value_points = points
                break
        score += value_points
    else:
        score += ORDER_VALUE_DEFAULT

    score += TIER_SCORES.get(customer_tier, 2)

    if has_prior_contact:
        score += REPEAT_CONTACT_BONUS

    if has_open_tickets >= 2:
        score += OPEN_TICKETS_HIGH
    elif has_open_tickets == 1:
        score += OPEN_TICKETS_LOW

    return score
