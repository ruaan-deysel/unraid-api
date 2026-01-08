"""Tests for custom exceptions."""

from __future__ import annotations

from unraid_api.exceptions import (
    UnraidAPIError,
    UnraidAuthenticationError,
    UnraidConnectionError,
    UnraidTimeoutError,
)


class TestUnraidAPIError:
    """Tests for UnraidAPIError."""

    def test_error_with_message_only(self) -> None:
        """Test error with message only."""
        error = UnraidAPIError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.errors == []

    def test_error_with_graphql_errors(self) -> None:
        """Test error with GraphQL error list."""
        graphql_errors = [
            {"message": "Field not found", "path": ["query", "field"]},
            {"message": "Invalid argument"},
        ]
        error = UnraidAPIError("GraphQL query failed", errors=graphql_errors)

        assert "GraphQL query failed" in str(error)
        assert "Field not found" in str(error)
        assert "(path: ['query', 'field'])" in str(error)
        assert "Invalid argument" in str(error)
        assert error.errors == graphql_errors

    def test_error_with_non_dict_errors(self) -> None:
        """Test error with non-dict error items."""
        errors = ["Simple error string", "Another error"]
        error = UnraidAPIError("Failed", errors=errors)  # type: ignore[arg-type]

        assert "Simple error string" in str(error)
        assert "Another error" in str(error)


class TestUnraidConnectionError:
    """Tests for UnraidConnectionError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = UnraidConnectionError()

        assert str(error) == "Failed to connect to Unraid server"

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = UnraidConnectionError("Cannot reach server at 192.168.1.100")

        assert str(error) == "Cannot reach server at 192.168.1.100"

    def test_is_unraid_api_error(self) -> None:
        """Test that it's a subclass of UnraidAPIError."""
        error = UnraidConnectionError()

        assert isinstance(error, UnraidAPIError)


class TestUnraidAuthenticationError:
    """Tests for UnraidAuthenticationError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = UnraidAuthenticationError()

        assert str(error) == "Authentication failed"

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = UnraidAuthenticationError("Invalid API key provided")

        assert str(error) == "Invalid API key provided"

    def test_is_unraid_api_error(self) -> None:
        """Test that it's a subclass of UnraidAPIError."""
        error = UnraidAuthenticationError()

        assert isinstance(error, UnraidAPIError)


class TestUnraidTimeoutError:
    """Tests for UnraidTimeoutError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = UnraidTimeoutError()

        assert str(error) == "Request timed out"

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = UnraidTimeoutError("Request timed out after 30 seconds")

        assert str(error) == "Request timed out after 30 seconds"

    def test_is_unraid_api_error(self) -> None:
        """Test that it's a subclass of UnraidAPIError."""
        error = UnraidTimeoutError()

        assert isinstance(error, UnraidAPIError)


class TestExceptionHierarchy:
    """Tests for exception hierarchy."""

    def test_all_exceptions_inherit_from_base(self) -> None:
        """Test that all exceptions inherit from UnraidAPIError."""
        exceptions = [
            UnraidConnectionError(),
            UnraidAuthenticationError(),
            UnraidTimeoutError(),
        ]

        for exc in exceptions:
            assert isinstance(exc, UnraidAPIError)
            assert isinstance(exc, Exception)

    def test_can_catch_all_with_base_exception(self) -> None:
        """Test that base exception catches all derived exceptions."""
        exceptions_to_test = [
            UnraidConnectionError,
            UnraidAuthenticationError,
            UnraidTimeoutError,
        ]

        for exc_class in exceptions_to_test:
            try:
                raise exc_class()
            except UnraidAPIError as e:
                assert isinstance(e, exc_class)
