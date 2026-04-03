from pydantic import BaseModel


class IncomingMessage(BaseModel):
    """Raw support message received from any channel."""

    message_id: str
    source_channel: str  # "email" | "chat" | "merchant_portal" | "api"
    sender_id: str
    sender_type: str  # "customer" | "merchant" | "internal"
    subject: str | None = None
    body: str
    metadata: dict = {}
