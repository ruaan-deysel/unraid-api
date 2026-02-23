"""Custom exceptions for the Unraid API client."""

from __future__ import annotations

from typing import Any


class UnraidAPIError(Exception):
    """Base exception for Unraid API errors."""

    def __init__(
        self,
        message: str,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message.
            errors: Optional list of GraphQL error objects.

        """
        super().__init__(message)
        self.message = message
        self.errors = errors or []

    def __str__(self) -> str:
        """Return string representation."""
        if self.errors:
            error_msgs = []
            for err in self.errors:
                if isinstance(err, dict):
                    msg = err.get("message", str(err))
                    path = err.get("path")
                    if path:
                        msg = f"{msg} (path: {path})"
                    error_msgs.append(msg)
                else:
                    error_msgs.append(str(err))
            return f"{self.message}: {'; '.join(error_msgs)}"
        return self.message


class UnraidConnectionError(UnraidAPIError):
    """Exception raised when connection to Unraid server fails."""

    def __init__(self, message: str = "Failed to connect to Unraid server") -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message.

        """
        super().__init__(message)


class UnraidSSLError(UnraidConnectionError):
    """Exception raised when SSL certificate verification fails.

    This exception is raised for SSL/TLS-related errors including:
    - Certificate verification failures
    - Certificate hostname mismatches
    - TLS handshake errors
    - Self-signed certificate issues

    Inherits from UnraidConnectionError for backwards compatibility,
    allowing it to be caught with either UnraidSSLError or
    UnraidConnectionError.
    """

    def __init__(self, message: str = "SSL certificate verification failed") -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message.

        """
        super().__init__(message)


class UnraidAuthenticationError(UnraidAPIError):
    """Exception raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed") -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message.

        """
        super().__init__(message)


class UnraidTimeoutError(UnraidAPIError):
    """Exception raised when a request times out."""

    def __init__(self, message: str = "Request timed out") -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message.

        """
        super().__init__(message)


class UnraidVersionError(UnraidAPIError):
    """Exception raised when the server version is incompatible.

    This exception is raised when the Unraid server or API version
    does not meet the minimum requirements for this library.
    """

    def __init__(self, message: str = "Incompatible server version") -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message.

        """
        super().__init__(message)
