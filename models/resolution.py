from typing import Literal

from pydantic import BaseModel

from .ticket import ParsedTicket


class AutoResolution(BaseModel):
    """Resolution payload for low-risk auto-resolved tickets."""

    action: Literal["auto_resolve"] = "auto_resolve"
    resolution_type: str
    response_template: str
    confidence: float
    requires_followup: bool = False


class QueuedReview(BaseModel):
    """Queued review for medium-risk tickets."""

    action: Literal["queue_for_review"] = "queue_for_review"
    assigned_team: str
    priority: Literal["normal", "elevated"]
    recommended_actions: list[str]
    context_summary: str
    sla_hours: int


class EscalationRequest(BaseModel):
    """Escalation request for high/critical-risk tickets."""

    action: Literal["escalate"] = "escalate"
    severity: Literal["high", "critical"]
    assigned_team: str
    escalation_reason: str
    proposed_actions: list[str]
    customer_impact: str
    requires_approval: bool = True
    alert_channels: list[str] = []


class TriageResult(BaseModel):
    """Final output of the full triage pipeline."""

    # Trace
    message_id: str
    execution_id: str | None = None

    # Pipeline results
    parsed_ticket: ParsedTicket
    risk_score: int
    risk_tier: Literal["low", "medium", "high", "critical"]

    # Routing outcome
    routing_decision: Literal["auto_resolve", "queue_for_review", "escalate"]
    resolution: AutoResolution | QueuedReview | EscalationRequest

    # Audit
    pipeline_duration_ms: int | None = None
    agents_invoked: list[str] = ["intake", "scorer", "router"]

    # Overrides applied
    overrides: list[str] = []
