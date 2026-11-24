from collections.abc import Iterator

import pytest
from pydantic import SecretStr

from src.config import settings
from tests.safety.conftest import _fake_google, clock  # noqa: F401  (same fixtures)


@pytest.fixture(autouse=True)
def _push_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", SecretStr("test-private-key"))
    yield
