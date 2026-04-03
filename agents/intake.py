"""Intake Agent — parses raw support messages into structured tickets."""

import os
import re
from datetime import datetime, timezone

from agentfield import Agent, AIConfig

from models.incoming import IncomingMessage
from models.ticket import ParsedTicket, TicketWithContext
from models.trace import TriageTrace
from validators.intake_validator import validate_intake

app = Agent(
    node_id="intake",
    agentfield_server=os.getenv("AGENTFIELD_URL", "http://localhost:8080"),
    version="1.0.0",
    ai_config=AIConfig(model="anthropic/claude-sonnet-4-20250514"),
)

SYSTEM_PROMPT = """You are a fulfillment support intake specialist. Your job is to read
customer and merchant messages about e-commerce orders and extract
structured information. Be precise about order IDs, SKUs, and tracking
numbers — only extract them if they are explicitly mentioned. Assess
customer sentiment honestly. If the message is ambiguous, lower your
extraction_confidence score. Never fabricate entity values."""

ORDER_ID_PATTERN = re.compile(r"ORD-\d{5,}")


@app.reasoner()
async def process_message(
    message_id: str,
    source_channel: str,
    sender_id: str,
    sender_type: str,
    body: str,
    subject: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Parse an incoming support message and route to the scorer agent."""
    metadata = metadata or {}

    # Initialize trace
    trace = TriageTrace(raw_input=body)
    trace.intake_start = datetime.now(timezone.utc).isoformat()

    msg = IncomingMessage(
        message_id=message_id,
        source_channel=source_channel,
        sender_id=sender_id,
        sender_type=sender_type,
        subject=subject,
        body=body,
        metadata=metadata,
    )

    # LLM extraction with Pydantic schema
    user_prompt = f"""Source: {msg.source_channel}
Sender: {msg.sender_id} ({msg.sender_type})
Subject: {msg.subject or '(none)'}

Message:
{msg.body}"""

    parsed: ParsedTicket = await app.ai(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        schema=ParsedTicket,
    )

    # Capture LLM reasoning in trace
    trace.intake_reasoning = (
        f"Classified as '{parsed.issue_category}' with sentiment '{parsed.customer_sentiment}'. "
        f"Summary: {parsed.summary}"
    )
    trace.intake_confidence = parsed.extraction_confidence

    # Post-LLM validation: verify order IDs match expected pattern
    parsed.order_ids = [
        oid for oid in parsed.order_ids if ORDER_ID_PATTERN.fullmatch(oid)
    ]

    # Snapshot the parsed ticket in the trace
    trace.parsed_ticket_snapshot = parsed.model_dump()

    # If extraction confidence is very low, flag for manual review
    if parsed.extraction_confidence < 0.5:
        # Still route through pipeline — the router will handle forced escalation
        pass

    # Run post-intake semantic validation
    await validate_intake(parsed, body, trace, app)

    trace.intake_end = datetime.now(timezone.utc).isoformat()

    # Build context from metadata
    context = TicketWithContext(
        ticket=parsed,
        order_value_usd=metadata.get("order_value_usd"),
        customer_tier=metadata.get("customer_tier", "standard"),
        customer_lifetime_orders=metadata.get("customer_lifetime_orders", 1),
        days_since_shipment=metadata.get("days_since_shipment"),
        carrier=metadata.get("carrier"),
        destination_region=metadata.get("destination_region"),
        is_subscription_order=metadata.get("is_subscription_order", False),
        has_open_tickets=metadata.get("has_open_tickets", 0),
    )

    # Call scorer agent, passing message_id and trace for end-to-end tracing
    result = await app.call(
        "scorer.score_ticket",
        message_id=message_id,
        ticket=parsed.model_dump(),
        order_value_usd=context.order_value_usd,
        customer_tier=context.customer_tier,
        customer_lifetime_orders=context.customer_lifetime_orders,
        days_since_shipment=context.days_since_shipment,
        carrier=context.carrier,
        destination_region=context.destination_region,
        is_subscription_order=context.is_subscription_order,
        has_open_tickets=context.has_open_tickets,
        trace=trace.model_dump(),
    )

    return result


if __name__ == "__main__":
    app.run()
