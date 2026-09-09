import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test environment
os.environ["APP_ENV"] = "test"
os.environ["AUTH_MODE"] = "mock"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.core.config import get_settings
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def test_settings():
    settings = get_settings()
    settings.APP_ENV = "test"
    settings.AUTH_MODE = "mock"
    return settings


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
