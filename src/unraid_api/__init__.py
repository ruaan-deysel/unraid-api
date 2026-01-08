"""Unraid API - Python client library for Unraid's official GraphQL API."""

from unraid_api.client import UnraidClient
from unraid_api.exceptions import (
    UnraidAPIError,
    UnraidAuthenticationError,
    UnraidConnectionError,
    UnraidTimeoutError,
)
from unraid_api.models import (
    ArrayCapacity,
    ArrayDisk,
    ContainerPort,
    DockerContainer,
    Metrics,
    Notification,
    ParityCheck,
    PhysicalDisk,
    Share,
    SystemInfo,
    UnraidArray,
    UPSDevice,
    VmDomain,
)

__all__ = [
    "ArrayCapacity",
    "ArrayDisk",
    "ContainerPort",
    "DockerContainer",
    "Metrics",
    "Notification",
    "ParityCheck",
    "PhysicalDisk",
    "Share",
    "SystemInfo",
    "UPSDevice",
    "UnraidAPIError",
    "UnraidArray",
    "UnraidAuthenticationError",
    "UnraidClient",
    "UnraidConnectionError",
    "UnraidTimeoutError",
    "VmDomain",
]

__version__ = "1.2.0"
