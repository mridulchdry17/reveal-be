"""Print a new VAPID key pair for .env (VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY).

Run once per environment: uv run python scripts/vapid_keys.py >> .env
Changing the keys later signs everyone out of notifications.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


key = ec.generate_private_key(ec.SECP256R1())
private = key.private_numbers().private_value.to_bytes(32, "big")
public = key.public_key().public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
)
print(f"VAPID_PUBLIC_KEY={b64(public)}")
print(f"VAPID_PRIVATE_KEY={b64(private)}")
