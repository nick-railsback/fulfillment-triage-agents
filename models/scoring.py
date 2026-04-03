from typing import Literal

from pydantic import BaseModel, Field

from .ticket import ParsedTicket, TicketWithContext


class LLMSeverityAssessment(BaseModel):
    """LLM's nuanced assessment of ticket severity beyond rule-based scoring."""

    escalation_risk: int = Field(ge=0, le=15)
    resolution_complexity: int = Field(ge=0, le=15)
    time_sensitivity: int = Field(ge=0, le=10)
    reasoning: str


class ScoredTicket(BaseModel):
    """Fully scored ticket ready for routing."""

    ticket: ParsedTicket
    context: TicketWithContext

    risk_score: int  # 0-100
    risk_tier: Literal["low", "medium", "high", "critical"]

    deterministic_score: int
    llm_severity: LLMSeverityAssessment

    recommended_actions: list[str]
    recommended_team: str | None = None

    scored_at: str  # ISO timestamp
