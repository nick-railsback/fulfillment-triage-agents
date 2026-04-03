"""Escalation Router Agent — deterministic routing with human-in-the-loop gating."""

import os
import time
from datetime import datetime, timezone

from agentfield import Agent, AIConfig

from models.scoring import ScoredTicket
from models.resolution import (
    AutoResolution,
    QueuedReview,
    EscalationRequest,
    TriageResult,
)
from models.trace import TriageTrace
from config.routing_rules import (
    TIER_ROUTING,
    SLA_HOURS,
    CATEGORY_TEAMS,
    evaluate_overrides,
    apply_overrides,
)
from validators.router_validator import validate_router

app = Agent(
    node_id="router",
    agentfield_server=os.getenv("AGENTFIELD_URL", "http://localhost:8080"),
    version="1.0.0",
    ai_config=AIConfig(model="anthropic/claude-sonnet-4-20250514"),
)

RESPONSE_TEMPLATE_PROMPT = """You are a customer support response writer. Write a brief, empathetic
response to a customer based on their issue. Match tone to sentiment:
concise for neutral inquiries, empathetic for frustrated/angry customers.
Keep it under 3 sentences. Do not make promises you can't keep."""


@app.reasoner()
async def route_ticket(
    scored_ticket: dict,
    message_id: str = "",
    trace: dict | None = None,
) -> dict:
    """Route a scored ticket to the appropriate resolution path."""
    start_time = time.time()

    scored = ScoredTicket(**scored_ticket)
    ticket = scored.ticket

    # Restore or create trace
    triage_trace = TriageTrace(**trace) if trace else TriageTrace()
    triage_trace.router_start = datetime.now(timezone.utc).isoformat()

    # Determine base routing from tier
    base_routing = TIER_ROUTING[scored.risk_tier]

    # Evaluate and apply overrides
    overrides = evaluate_overrides(scored)
    final_routing, override_names = apply_overrides(base_routing, overrides)

    # Record overrides in trace
    triage_trace.overrides_applied = [
        {"rule": name, "reason": f"Override applied: {name}"}
        for name in override_names
    ]

    # Capture router reasoning
    triage_trace.router_reasoning = (
        f"Base routing for tier '{scored.risk_tier}': {base_routing}. "
        f"Overrides: {override_names or 'none'}. "
        f"Final routing: {final_routing}."
    )

    # Determine assigned team
    assigned_team = scored.recommended_team or CATEGORY_TEAMS.get(
        ticket.issue_category, "customer_success"
    )

    # Execute the appropriate resolution path
    hitl_triggered = False
    if final_routing == "auto_resolve":
        resolution = await _auto_resolve(scored, assigned_team)
    elif final_routing == "queue_for_review":
        resolution = _queue_for_review(scored, assigned_team)
    else:
        resolution = await _escalate(scored, assigned_team, message_id)
        hitl_triggered = True
        triage_trace.hitl_triggered = True
        triage_trace.hitl_outcome = "pending"  # Will be set by escalation handler

    triage_trace.final_routing_decision = final_routing

    # Run post-router semantic validation
    validate_router(scored, final_routing, override_names, hitl_triggered, triage_trace)

    triage_trace.router_end = datetime.now(timezone.utc).isoformat()

    elapsed_ms = int((time.time() - start_time) * 1000)
    triage_trace.total_latency_ms = elapsed_ms

    result = TriageResult(
        message_id=message_id,
        parsed_ticket=ticket,
        risk_score=scored.risk_score,
        risk_tier=scored.risk_tier,
        routing_decision=final_routing,
        resolution=resolution,
        pipeline_duration_ms=elapsed_ms,
        overrides=override_names,
        trace=triage_trace,
    )

    # Call verifier agent for post-pipeline audit
    try:
        verification = await app.call(
            "verifier.verify_triage",
            triage_result=result.model_dump(),
            raw_message=triage_trace.raw_input,
        )
        # Attach verification result — update the result dict directly
        result_dict = result.model_dump()
        result_dict["verification_result"] = verification
        return result_dict
    except Exception as exc:
        # Verifier is non-blocking — log and return result without verification
        import logging
        logging.getLogger("router").warning("Verifier call failed: %s", exc)
        return result.model_dump()


async def _auto_resolve(scored: ScoredTicket, assigned_team: str) -> AutoResolution:
    """Generate an auto-resolution for low-risk tickets."""
    ticket = scored.ticket

    # Use LLM to generate a customer-facing response template
    response_text = await app.ai(
        system=RESPONSE_TEMPLATE_PROMPT,
        user=f"""Issue: {ticket.issue_category}
Summary: {ticket.summary}
Customer ask: {ticket.verbatim_ask}
Sentiment: {ticket.customer_sentiment}""",
    )

    # Map categories to resolution types
    resolution_types = {
        "tracking_inquiry": "send_tracking_link",
        "shipping_delay": "send_tracking_link",
        "return_request": "trigger_return_label",
        "address_change": "update_address",
        "general_inquiry": "send_faq",
        "inventory_question": "send_faq",
    }

    return AutoResolution(
        resolution_type=resolution_types.get(ticket.issue_category, "send_faq"),
        response_template=str(response_text),
        confidence=ticket.extraction_confidence,
        requires_followup=ticket.extraction_confidence < 0.8,
    )


def _queue_for_review(scored: ScoredTicket, assigned_team: str) -> QueuedReview:
    """Queue a medium-risk ticket for human review."""
    ticket = scored.ticket

    context_summary = (
        f"{ticket.issue_category.replace('_', ' ').title()} issue. "
        f"{ticket.summary} "
        f"Customer sentiment: {ticket.customer_sentiment}. "
        f"Risk score: {scored.risk_score}/100 ({scored.risk_tier}). "
        f"Recommended team: {assigned_team}."
    )

    return QueuedReview(
        assigned_team=assigned_team,
        priority="elevated" if scored.risk_score > 40 else "normal",
        recommended_actions=scored.recommended_actions,
        context_summary=context_summary,
        sla_hours=SLA_HOURS.get(scored.risk_tier, 24),
    )


async def _escalate(scored: ScoredTicket, assigned_team: str, message_id: str = "") -> EscalationRequest:
    """Escalate a high/critical ticket with human-in-the-loop gating."""
    ticket = scored.ticket
    severity = "critical" if scored.risk_tier == "critical" else "high"

    escalation_reason = (
        f"{severity.upper()} severity: {ticket.summary} "
        f"(risk score {scored.risk_score}/100). "
        f"LLM reasoning: {scored.llm_severity.reasoning}"
    )

    customer_impact = (
        f"Customer ({scored.context.customer_tier} tier) is {ticket.customer_sentiment}. "
        f"Issue: {ticket.issue_category.replace('_', ' ')}."
    )

    if scored.context.order_value_usd:
        customer_impact += f" Order value: ${scored.context.order_value_usd:,.2f}."

    alert_channels = []
    if severity == "critical":
        alert_channels = ["slack", "pagerduty"]

    escalation = EscalationRequest(
        severity=severity,
        assigned_team=assigned_team,
        escalation_reason=escalation_reason,
        proposed_actions=scored.recommended_actions,
        customer_impact=customer_impact,
        alert_channels=alert_channels,
    )

    # Human-in-the-loop gate via app.pause
    review = await app.pause(
        approval_request_id=f"escalation-{message_id}-{scored.ticket.issue_category}",
        expires_in_hours=24 if severity == "high" else 4,
    )

    # Handle human decision
    if hasattr(review, "decision") and review.decision == "rejected":
        escalation.requires_approval = False
        escalation.escalation_reason = (
            f"REJECTED by reviewer: {getattr(review, 'feedback', 'No feedback')}. "
            f"Original: {escalation.escalation_reason}"
        )

    return escalation


if __name__ == "__main__":
    app.run()
