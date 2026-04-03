"""Verification Agent — adversarial post-pipeline audit of triage decisions."""

import os

from agentfield import Agent, AIConfig

from models.trace import VerificationResult

app = Agent(
    node_id="verifier",
    agentfield_server=os.getenv("AGENTFIELD_URL", "http://localhost:8080"),
    version="1.0.0",
    ai_config=AIConfig(model="anthropic/claude-sonnet-4-20250514"),
)

VERIFIER_SYSTEM_PROMPT = """You are a skeptical quality assurance auditor for a fulfillment support
triage system. Your job is to find reasons the triage might be WRONG.
Do not give the pipeline the benefit of the doubt. Look for:

- Category misclassification (does the raw message actually describe this issue type?)
- Risk assessment errors (was the urgency over- or under-estimated?)
- Routing mistakes (should this ticket have gone to a different path?)
- Trace anomalies (unusual latency, conflicting validation results, overrides that seem wrong)

Be adversarial but fair. If the triage is genuinely correct, say so — but only after
actively trying to find problems. Your assessment directly affects whether misrouted
tickets reach customers, so err on the side of flagging concerns."""


@app.reasoner()
async def verify_triage(triage_result: dict, raw_message: str = "") -> dict:
    """Audit a completed triage result for quality and correctness."""
    # Build a concise evaluation prompt from the triage result
    parsed = triage_result.get("parsed_ticket", {})
    trace = triage_result.get("trace") or {}
    validation_results = trace.get("validation_results", [])

    # Summarize validation check outcomes
    validation_summary = ""
    if validation_results:
        failures = [v for v in validation_results if v.get("status") == "fail"]
        warnings = [v for v in validation_results if v.get("status") == "warning"]
        if failures:
            validation_summary += f"\nVALIDATION FAILURES:\n"
            for v in failures:
                validation_summary += f"  - {v['check_name']}: {v['details']}\n"
        if warnings:
            validation_summary += f"\nVALIDATION WARNINGS:\n"
            for v in warnings:
                validation_summary += f"  - {v['check_name']}: {v['details']}\n"

    eval_prompt = f"""ORIGINAL RAW MESSAGE:
{raw_message}

TRIAGE PIPELINE OUTPUT:
- Category: {parsed.get('issue_category')}
- Sentiment: {parsed.get('customer_sentiment')}
- Extraction Confidence: {parsed.get('extraction_confidence')}
- Risk Score: {triage_result.get('risk_score')}/100
- Risk Tier: {triage_result.get('risk_tier')}
- Routing Decision: {triage_result.get('routing_decision')}
- Overrides Applied: {triage_result.get('overrides', [])}
- Pipeline Duration: {triage_result.get('pipeline_duration_ms')}ms

SCORER REASONING:
{trace.get('scorer_reasoning', 'N/A')}

ROUTER REASONING:
{trace.get('router_reasoning', 'N/A')}
{validation_summary}
Evaluate the quality of this triage. Consider each dimension carefully."""

    verification: VerificationResult = await app.ai(
        system=VERIFIER_SYSTEM_PROMPT,
        user=eval_prompt,
        schema=VerificationResult,
    )

    return verification.model_dump()


if __name__ == "__main__":
    app.run()
