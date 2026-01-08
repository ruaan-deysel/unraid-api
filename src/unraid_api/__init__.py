"""Unraid API - Python client library for Unraid's official GraphQL API."""

from unraid_api.client import UnraidClient
from unraid_api.exceptions import (
    UnraidAPIError,
    UnraidAuthenticationError,
    UnraidConnectionError,
)

__all__ = [
    "UnraidAPIError",
    "UnraidAuthenticationError",
    "UnraidClient",
    "UnraidConnectionError",
]

__version__ = "0.1.0"
