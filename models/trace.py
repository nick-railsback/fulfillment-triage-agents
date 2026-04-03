"""Trace and validation models for pipeline observability."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Outcome of a single semantic validation check."""

    check_name: str
    status: Literal["pass", "fail", "warning"]
    details: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TriageTrace(BaseModel):
    """Observability trace that travels with a ticket through the entire pipeline."""

    # Identity
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    raw_input: str = ""

    # Timestamps at each agent boundary
    intake_start: str | None = None
    intake_end: str | None = None
    scorer_start: str | None = None
    scorer_end: str | None = None
    router_start: str | None = None
    router_end: str | None = None

    # LLM reasoning captured at each stage
    intake_reasoning: str | None = None
    scorer_reasoning: str | None = None
    router_reasoning: str | None = None

    # Confidence at each stage
    intake_confidence: float | None = None
    scorer_confidence: float | None = None

    # Intermediate model snapshots (serialized dicts)
    parsed_ticket_snapshot: dict | None = None
    scored_ticket_snapshot: dict | None = None

    # Business rule overrides that fired
    overrides_applied: list[dict] = []  # [{"rule": str, "reason": str}, ...]

    # Human-in-the-loop
    hitl_triggered: bool = False
    hitl_outcome: str | None = None  # "approved", "rejected", or None

    # Final routing
    final_routing_decision: str | None = None

    # Total pipeline latency (ms)
    total_latency_ms: int | None = None

    # Accumulated validation results
    validation_results: list[ValidationResult] = []


class VerificationResult(BaseModel):
    """Output of the Verification Agent's post-pipeline audit."""

    overall_verdict: Literal["pass", "fail", "needs_review"]
    category_assessment: str
    scoring_assessment: str
    routing_assessment: str
    trace_anomalies: list[str] = []
    confidence: float
    rationale: str
