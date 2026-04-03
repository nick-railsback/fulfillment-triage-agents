# fulfillment-triage-agents

A multi-agent fulfillment support triage system built on [AgentField](https://agentfield.ai/). Three coordinating AI agents process incoming support messages related to e-commerce fulfillment, extract structured data, score risk and urgency, and route to the appropriate resolution path.

## Why

E-commerce fulfillment support is high-volume, high-stakes, and currently relies on manual triage. AI agents can classify, score, and route 80%+ of tickets instantly while ensuring high-risk cases always get human eyes.

## Architecture

```
HTTP Client → AgentField Control Plane
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
    Intake       Scorer     Escalation
    Agent        Agent      Router Agent
    (parse)      (score)    (route)
```

**Flow:** Client POSTs a raw message → **Intake** extracts structured ticket data via LLM → **Scorer** computes hybrid risk score (deterministic rules + LLM severity) → **Router** applies business rules and routes to auto-resolve, queue, or human escalation.

### Key patterns demonstrated

- **Structured LLM output** — Pydantic v2 schemas via `app.ai(schema=...)`, not freeform text
- **Multi-agent orchestration** — agents call each other via `app.call()`
- **Hybrid scoring** — deterministic business rules + LLM-assessed contextual severity
- **Human-in-the-loop** — `app.pause` gates high/critical tickets on human approval
- **Business rule overrides** — policy rules that trump AI scores (billing disputes, enterprise tier, low confidence)
- **Auditable traces** — full pipeline results in `TriageResult` with overrides and timing

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# 2. Start everything
docker compose up --build

# 3. Run a test scenario
python scripts/run_scenario.py tests/scenarios/low_risk_tracking.json

# 4. Run all scenarios
python scripts/run_all_scenarios.py
```

For local development without Docker, run `af server` in one terminal, then start each agent:

```bash
python agents/intake.py
python agents/scorer.py
python agents/router.py
```

## Test Scenarios

| Scenario | File | Expected Category | Expected Routing | Key Feature |
|----------|------|-------------------|-----------------|-------------|
| Low-risk tracking | `low_risk_tracking.json` | tracking_inquiry | auto_resolve | Happy path |
| Wrong item | `medium_wrong_item.json` | wrong_item | queue_for_review | Medium risk scoring |
| Enterprise damage | `high_risk_enterprise.json` | damaged_item | escalate (app.pause) | Critical + human gate |
| Billing override | `override_billing.json` | billing_dispute | escalate (override) | Business rule override |
| Ambiguous angry | `ambiguous_angry.json` | other | escalate (override) | Low confidence forced escalation |

## Human-in-the-Loop (app.pause)

When the router encounters a high or critical ticket, it invokes `app.pause` to gate execution on human approval. The agent suspends and waits for a human operator to review the proposed actions via the AgentField dashboard (http://localhost:8080) or API.

The human can approve, modify, or reject the proposed actions. Only after human input does execution resume and the final `TriageResult` return to the caller.

## Project Structure

```
agents/
  intake.py          # Message parsing and entity extraction
  scorer.py          # Hybrid risk scoring (deterministic + LLM)
  router.py          # Routing + human-in-the-loop gating
models/
  incoming.py        # IncomingMessage schema
  ticket.py          # ParsedTicket, TicketWithContext
  scoring.py         # LLMSeverityAssessment, ScoredTicket
  resolution.py      # AutoResolution, QueuedReview, EscalationRequest, TriageResult
config/
  scoring_weights.py # Tunable deterministic scoring factors
  routing_rules.py   # Override rules and tier thresholds
tests/scenarios/     # 5 test fixture JSON files
scripts/             # CLI tools for running scenarios
```

## Stack

Python 3.11+ · AgentField SDK · Pydantic v2 · Claude Sonnet (via `app.ai()`) · Docker Compose
