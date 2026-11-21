import pytest

from src.auth import google
from src.exceptions import Unauthenticated


async def test_sign_in_is_disabled_without_a_client_id() -> None:
    # Tests run with no GOOGLE_CLIENT_ID, like a fresh checkout.
    with pytest.raises(Unauthenticated, match="not configured"):
        await google.verify_credential("anything")
