"""Post-Router semantic validation.

Checks that routing decisions align with scores and policies.
"""

from models.scoring import ScoredTicket
from models.trace import TriageTrace, ValidationResult
from config.validation_thresholds import FORBIDDEN_ROUTING, INTAKE_CONFIDENCE_FLOOR


def validate_router(
    scored: ScoredTicket,
    routing_decision: str,
    override_names: list[str],
    hitl_triggered: bool,
    trace: TriageTrace,
) -> list[ValidationResult]:
    """Run all post-router semantic checks."""
    results: list[ValidationResult] = []

    results.append(_check_routing_score_alignment(scored, routing_decision))
    results.append(_check_override_legitimacy(scored, override_names))
    results.append(_check_hitl_policy(scored, routing_decision, hitl_triggered))

    trace.validation_results.extend(results)
    return results


def _check_routing_score_alignment(
    scored: ScoredTicket,
    routing_decision: str,
) -> ValidationResult:
    """Verify the routing decision doesn't violate tier-based policy."""
    forbidden = FORBIDDEN_ROUTING.get(scored.risk_tier, set())

    if routing_decision in forbidden:
        return ValidationResult(
            check_name="router_score_alignment",
            status="fail",
            details=(
                f"Routing '{routing_decision}' is forbidden for "
                f"risk tier '{scored.risk_tier}' (score {scored.risk_score})"
            ),
        )

    return ValidationResult(
        check_name="router_score_alignment",
        status="pass",
        details=(
            f"Routing '{routing_decision}' is valid for "
            f"risk tier '{scored.risk_tier}'"
        ),
    )


def _check_override_legitimacy(
    scored: ScoredTicket,
    override_names: list[str],
) -> ValidationResult:
    """Verify that overrides that fired are legitimate given ticket data."""
    issues = []
    ticket = scored.ticket
    ctx = scored.context

    for name in override_names:
        if name == "billing_dispute_high_value":
            if ticket.issue_category != "billing_dispute" or (ctx.order_value_usd or 0) <= 200:
                issues.append(
                    f"Override '{name}' fired but category is '{ticket.issue_category}' "
                    f"and order value is ${ctx.order_value_usd}"
                )

        elif name == "enterprise_tier_minimum":
            if ctx.customer_tier != "enterprise":
                issues.append(
                    f"Override '{name}' fired but customer tier is '{ctx.customer_tier}'"
                )

        elif name == "low_confidence_escalation":
            if ticket.extraction_confidence >= INTAKE_CONFIDENCE_FLOOR:
                issues.append(
                    f"Override '{name}' fired but confidence is {ticket.extraction_confidence}"
                )

        elif name == "repeat_contact_escalation":
            if not ticket.has_prior_contact or ctx.has_open_tickets < 2:
                issues.append(
                    f"Override '{name}' fired but prior_contact={ticket.has_prior_contact}, "
                    f"open_tickets={ctx.has_open_tickets}"
                )

    if issues:
        return ValidationResult(
            check_name="router_override_legitimacy",
            status="fail",
            details="; ".join(issues),
        )

    override_summary = ", ".join(override_names) if override_names else "none"
    return ValidationResult(
        check_name="router_override_legitimacy",
        status="pass",
        details=f"All overrides legitimate: {override_summary}",
    )


def _check_hitl_policy(
    scored: ScoredTicket,
    routing_decision: str,
    hitl_triggered: bool,
) -> ValidationResult:
    """Verify human-in-the-loop was triggered when policy requires it."""
    should_trigger = routing_decision == "escalate"

    if should_trigger and not hitl_triggered:
        return ValidationResult(
            check_name="router_hitl_policy",
            status="warning",
            details=(
                f"Routing is '{routing_decision}' but HITL was not triggered. "
                f"Risk tier: {scored.risk_tier}"
            ),
        )

    if not should_trigger and hitl_triggered:
        return ValidationResult(
            check_name="router_hitl_policy",
            status="warning",
            details=f"HITL triggered but routing is '{routing_decision}' (not escalate)",
        )

    return ValidationResult(
        check_name="router_hitl_policy",
        status="pass",
        details=f"HITL policy correct: triggered={hitl_triggered}, routing={routing_decision}",
    )
