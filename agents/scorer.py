"""Scorer Agent — hybrid deterministic + LLM risk scoring."""

import os
from datetime import datetime, timezone

from agentfield import Agent, AIConfig

from models.ticket import ParsedTicket, TicketWithContext
from models.scoring import LLMSeverityAssessment, ScoredTicket
from config.scoring_weights import compute_deterministic_score
from config.routing_rules import score_to_tier, CATEGORY_TEAMS

app = Agent(
    node_id="scorer",
    agentfield_server=os.getenv("AGENTFIELD_URL", "http://localhost:8080"),
    version="1.0.0",
    ai_config=AIConfig(model="anthropic/claude-sonnet-4-20250514"),
)

SEVERITY_SYSTEM_PROMPT = """You are a fulfillment operations risk analyst. Given a parsed support
ticket and business context, assess the severity factors that rules
alone can't capture. Consider: Will this customer escalate publicly?
Does resolution require multiple teams? Is there a hard deadline
(e.g., a gift, perishable product, event)? Be calibrated — most
tickets are routine. Reserve high scores for genuinely complex or
high-stakes situations."""


@app.reasoner()
async def score_ticket(
    ticket: dict,
    message_id: str = "",
    order_value_usd: float | None = None,
    customer_tier: str = "standard",
    customer_lifetime_orders: int = 1,
    days_since_shipment: int | None = None,
    carrier: str | None = None,
    destination_region: str | None = None,
    is_subscription_order: bool = False,
    has_open_tickets: int = 0,
) -> dict:
    """Score a parsed ticket and route to the escalation router."""
    parsed = ParsedTicket(**ticket)

    context = TicketWithContext(
        ticket=parsed,
        order_value_usd=order_value_usd,
        customer_tier=customer_tier,
        customer_lifetime_orders=customer_lifetime_orders,
        days_since_shipment=days_since_shipment,
        carrier=carrier,
        destination_region=destination_region,
        is_subscription_order=is_subscription_order,
        has_open_tickets=has_open_tickets,
    )

    # A. Deterministic score (0-60)
    deterministic_score = compute_deterministic_score(
        issue_category=parsed.issue_category,
        sentiment=parsed.customer_sentiment,
        order_value_usd=order_value_usd,
        customer_tier=customer_tier,
        has_prior_contact=parsed.has_prior_contact,
        has_open_tickets=has_open_tickets,
    )

    # B. LLM severity assessment (0-40)
    severity_prompt = f"""Ticket Summary: {parsed.summary}
Customer Ask: {parsed.verbatim_ask}
Category: {parsed.issue_category}
Sentiment: {parsed.customer_sentiment}
Order Value: ${order_value_usd or 'unknown'}
Customer Tier: {customer_tier}
Days Since Issue: {parsed.days_since_issue or 'unknown'}
Prior Contact: {parsed.has_prior_contact}
Open Tickets: {has_open_tickets}
Subscription Order: {is_subscription_order}"""

    llm_severity: LLMSeverityAssessment = await app.ai(
        system=SEVERITY_SYSTEM_PROMPT,
        user=severity_prompt,
        schema=LLMSeverityAssessment,
    )

    # Composite score
    risk_score = min(
        100,
        deterministic_score
        + llm_severity.escalation_risk
        + llm_severity.resolution_complexity
        + llm_severity.time_sensitivity,
    )

    risk_tier = score_to_tier(risk_score)
    recommended_team = CATEGORY_TEAMS.get(parsed.issue_category, "customer_success")

    scored = ScoredTicket(
        ticket=parsed,
        context=context,
        risk_score=risk_score,
        risk_tier=risk_tier,
        deterministic_score=deterministic_score,
        llm_severity=llm_severity,
        recommended_actions=_suggest_actions(parsed.issue_category, risk_tier),
        recommended_team=recommended_team,
        scored_at=datetime.now(timezone.utc).isoformat(),
    )

    # Call router agent, forwarding message_id for tracing
    result = await app.call(
        "router.route_ticket",
        message_id=message_id,
        scored_ticket=scored.model_dump(),
    )

    return result


def _suggest_actions(category: str, tier: str) -> list[str]:
    """Generate recommended actions based on category and tier."""
    actions: list[str] = []

    category_actions = {
        "shipping_delay": ["Check carrier tracking status", "Send proactive update to customer"],
        "wrong_item": ["Initiate return label generation", "Queue correct item for reshipment"],
        "damaged_item": ["File carrier damage claim", "Initiate replacement shipment"],
        "missing_item": ["Verify shipment contents with warehouse", "Initiate replacement"],
        "address_change": ["Update shipping address if not yet shipped", "Contact carrier for redirect"],
        "return_request": ["Generate return label", "Process return authorization"],
        "refund_request": ["Review order for refund eligibility", "Process refund if eligible"],
        "tracking_inquiry": ["Provide current tracking information"],
        "inventory_question": ["Check current inventory levels", "Provide availability estimate"],
        "billing_dispute": ["Review transaction records", "Escalate to billing team"],
        "general_inquiry": ["Review and respond to inquiry"],
    }

    actions.extend(category_actions.get(category, ["Review and assess"]))

    if tier in ("high", "critical"):
        actions.append("Assign to senior agent for priority handling")

    return actions


if __name__ == "__main__":
    app.run()
