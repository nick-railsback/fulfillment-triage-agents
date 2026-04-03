from typing import Literal

from pydantic import BaseModel


class ParsedTicket(BaseModel):
    """Structured extraction from a raw support message."""

    # Issue classification
    issue_category: Literal[
        "shipping_delay",
        "wrong_item",
        "damaged_item",
        "missing_item",
        "address_change",
        "return_request",
        "refund_request",
        "tracking_inquiry",
        "inventory_question",
        "billing_dispute",
        "general_inquiry",
        "other",
    ]

    # Extracted entities
    order_ids: list[str]
    sku_references: list[str]
    tracking_numbers: list[str]

    # Sentiment and tone
    customer_sentiment: Literal["positive", "neutral", "frustrated", "angry", "urgent"]

    # Temporal signals
    days_since_issue: int | None = None
    has_prior_contact: bool = False

    # Message summary
    summary: str
    verbatim_ask: str

    # Confidence
    extraction_confidence: float


class TicketWithContext(BaseModel):
    """ParsedTicket enriched with business context for scoring."""

    ticket: ParsedTicket

    # Simulated business context (in production, from internal APIs)
    order_value_usd: float | None = None
    customer_tier: Literal["standard", "vip", "enterprise"] = "standard"
    customer_lifetime_orders: int = 1
    days_since_shipment: int | None = None
    carrier: str | None = None
    destination_region: str | None = None
    is_subscription_order: bool = False
    has_open_tickets: int = 0
