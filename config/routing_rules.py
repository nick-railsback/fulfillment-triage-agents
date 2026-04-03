"""Routing override rules and tier thresholds for the Escalation Router.

Override rules are evaluated in order. Each returns a tuple of
(should_override, new_minimum_routing, override_name) or None.
"""

from typing import Literal

from models.scoring import ScoredTicket


# Risk tier thresholds
TIER_THRESHOLDS: list[tuple[int, str]] = [
    (76, "critical"),
    (51, "high"),
    (26, "medium"),
    (0, "low"),
]

# Routing map: tier -> routing decision
TIER_ROUTING: dict[str, str] = {
    "low": "auto_resolve",
    "medium": "queue_for_review",
    "high": "escalate",
    "critical": "escalate",
}

# SLA hours by tier
SLA_HOURS: dict[str, int] = {
    "low": 72,
    "medium": 24,
    "high": 4,
    "critical": 1,
}

# Team assignment by category
CATEGORY_TEAMS: dict[str, str] = {
    "shipping_delay": "shipping_ops",
    "wrong_item": "shipping_ops",
    "damaged_item": "shipping_ops",
    "missing_item": "shipping_ops",
    "address_change": "shipping_ops",
    "return_request": "returns",
    "refund_request": "returns",
    "tracking_inquiry": "shipping_ops",
    "inventory_question": "inventory",
    "billing_dispute": "fraud",
    "general_inquiry": "customer_success",
    "other": "customer_success",
}

# Routing hierarchy for override bumps
ROUTING_HIERARCHY: list[str] = ["auto_resolve", "queue_for_review", "escalate"]


def score_to_tier(score: int) -> str:
    """Convert a numeric risk score to a tier label."""
    for threshold, tier in TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "low"


def evaluate_overrides(scored_ticket: ScoredTicket) -> list[tuple[str, str]]:
    """Evaluate override rules against a scored ticket.

    Returns a list of (override_name, minimum_routing) tuples for all
    overrides that triggered.
    """
    overrides: list[tuple[str, str]] = []
    ticket = scored_ticket.ticket
    ctx = scored_ticket.context

    # Billing dispute over $200 → always escalate
    if (
        ticket.issue_category == "billing_dispute"
        and ctx.order_value_usd is not None
        and ctx.order_value_usd > 200
    ):
        overrides.append(("billing_dispute_high_value", "escalate"))

    # Enterprise tier → minimum queue_for_review (never auto-resolve)
    if ctx.customer_tier == "enterprise":
        overrides.append(("enterprise_tier_minimum", "queue_for_review"))

    # Low extraction confidence → always escalate
    if ticket.extraction_confidence < 0.6:
        overrides.append(("low_confidence_escalation", "escalate"))

    # Repeat contact with multiple open tickets → bump up one tier (relative)
    if ticket.has_prior_contact and ctx.has_open_tickets >= 2:
        overrides.append(("repeat_contact_escalation", "+1"))

    return overrides


def apply_overrides(
    base_routing: str, overrides: list[tuple[str, str]]
) -> tuple[str, list[str]]:
    """Apply override rules, returning the final routing decision and list of override names.

    The highest-priority override wins (furthest right in the hierarchy).
    """
    final_routing = base_routing
    override_names: list[str] = []

    for name, minimum_routing in overrides:
        override_names.append(name)
        if minimum_routing == "+1":
            # Relative bump: move one step up the hierarchy
            current_idx = ROUTING_HIERARCHY.index(final_routing)
            if current_idx < len(ROUTING_HIERARCHY) - 1:
                final_routing = ROUTING_HIERARCHY[current_idx + 1]
        elif ROUTING_HIERARCHY.index(minimum_routing) > ROUTING_HIERARCHY.index(
            final_routing
        ):
            final_routing = minimum_routing

    return final_routing, override_names
