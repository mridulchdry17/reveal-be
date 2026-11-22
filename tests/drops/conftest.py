from collections.abc import Iterator

import pytest

from src.auth.dependencies import get_google_verifier
from src.clock import now
from src.main import app
from tests.auth.test_auth import fake_verify
from tests.drops.helpers import Clock


@pytest.fixture(autouse=True)
def _fake_google() -> Iterator[None]:
    app.dependency_overrides[get_google_verifier] = lambda: fake_verify
    yield
    app.dependency_overrides.pop(get_google_verifier, None)


@pytest.fixture(autouse=True)
def clock() -> Iterator[Clock]:
    fake = Clock()
    app.dependency_overrides[now] = lambda: fake()
    yield fake
    app.dependency_overrides.pop(now, None)
