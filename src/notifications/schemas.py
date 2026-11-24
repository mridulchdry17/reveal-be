from pydantic import BaseModel, Field


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class SubscriptionIn(BaseModel):
    """Exactly what the browser's PushSubscription.toJSON() gives."""

    endpoint: str = Field(min_length=1, max_length=1000, pattern=r"^https://")
    keys: PushKeys


class Unsubscribe(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1000)


class PushConfig(BaseModel):
    public_key: str | None = Field(
        description="VAPID public key for PushManager.subscribe. Null: push is off here"
    )
