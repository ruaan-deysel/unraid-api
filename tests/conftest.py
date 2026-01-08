"""Shared pytest fixtures for Unraid API tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from unraid_api import UnraidClient


@pytest.fixture
def api_key() -> str:
    """Return a test API key."""
    return "test-api-key-12345"


@pytest.fixture
def host() -> str:
    """Return a test host."""
    return "192.168.1.100"


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock aiohttp session."""
    session = MagicMock()
    session.close = AsyncMock()
    session.post = MagicMock()
    session.get = MagicMock()
    return session


@pytest.fixture
def mock_client(host: str, api_key: str, mock_session: MagicMock) -> UnraidClient:
    """Create an UnraidClient with a mocked session."""
    client = UnraidClient(host, api_key, session=mock_session)
    # Pre-set resolved URL to skip discovery
    client._resolved_url = f"https://{host}/graphql"
    return client


@pytest.fixture
def graphql_success_response() -> dict[str, Any]:
    """Return a successful GraphQL response structure."""
    return {"data": {"online": True}}


@pytest.fixture
def graphql_error_response() -> dict[str, Any]:
    """Return a GraphQL error response structure."""
    return {
        "errors": [
            {
                "message": "Test error message",
                "path": ["test", "path"],
            }
        ]
    }


@pytest.fixture
def version_response() -> dict[str, Any]:
    """Return a version query response."""
    return {
        "data": {
            "info": {
                "versions": {
                    "core": {
                        "unraid": "7.2.0",
                        "api": "4.21.0",
                    }
                }
            }
        }
    }


@pytest.fixture
def container_response() -> dict[str, Any]:
    """Return a container mutation response."""
    return {
        "data": {
            "docker": {
                "start": {
                    "id": "container:abc123",
                    "state": "RUNNING",
                    "status": "Up 5 seconds",
                }
            }
        }
    }


@pytest.fixture
def array_response() -> dict[str, Any]:
    """Return an array query response."""
    return {
        "data": {
            "array": {
                "state": "STARTED",
                "capacity": {
                    "kilobytes": {
                        "total": 1000000000,
                        "used": 500000000,
                        "free": 500000000,
                    }
                },
                "disks": [
                    {
                        "id": "disk:1",
                        "name": "Disk 1",
                        "status": "DISK_OK",
                        "temp": 35,
                        "isSpinning": True,
                    }
                ],
            }
        }
    }
