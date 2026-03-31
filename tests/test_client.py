"""Tests for UnraidClient initialization and configuration."""

from __future__ import annotations

from unraid_api import UnraidClient


class TestClientInitialization:
    """Tests for client initialization."""

    def test_init_with_required_params(self, host: str, api_key: str) -> None:
        """Test client initialization with required parameters."""
        client = UnraidClient(host, api_key)

        assert client.host == host
        assert client._auth_headers == {"x-api-key": api_key}
        assert client.http_port == 80
        assert client.https_port == 443
        assert client.verify_ssl is True
        assert client.timeout == 30
        assert client._session is None
        assert client._owns_session is True
        assert client._resolved_url is None

    def test_init_with_custom_ports(self, host: str, api_key: str) -> None:
        """Test client initialization with custom ports."""
        client = UnraidClient(
            host,
            api_key,
            http_port=8080,
            https_port=8443,
        )

        assert client.http_port == 8080
        assert client.https_port == 8443

    def test_init_with_ssl_disabled(self, host: str, api_key: str) -> None:
        """Test client initialization with SSL verification disabled."""
        client = UnraidClient(host, api_key, verify_ssl=False)

        assert client.verify_ssl is False

    def test_init_with_custom_timeout(self, host: str, api_key: str) -> None:
        """Test client initialization with custom timeout."""
        client = UnraidClient(host, api_key, timeout=60)

        assert client.timeout == 60

    def test_init_strips_host_whitespace(self, api_key: str) -> None:
        """Test that host whitespace is stripped."""
        client = UnraidClient("  192.168.1.100  ", api_key)

        assert client.host == "192.168.1.100"

    def test_init_invalid_http_port(self, host: str, api_key: str) -> None:
        """Test init rejects invalid http_port."""
        import pytest

        with pytest.raises(ValueError, match="http_port"):
            UnraidClient(host, api_key, http_port=0)

    def test_init_invalid_https_port(self, host: str, api_key: str) -> None:
        """Test init rejects invalid https_port."""
        import pytest

        with pytest.raises(ValueError, match="https_port"):
            UnraidClient(host, api_key, https_port=70000)

    def test_init_invalid_timeout(self, host: str, api_key: str) -> None:
        """Test init rejects invalid timeout."""
        import pytest

        with pytest.raises(ValueError, match="timeout"):
            UnraidClient(host, api_key, timeout=0)

    def test_init_with_injected_session(
        self, host: str, api_key: str, mock_session: object
    ) -> None:
        """Test client initialization with injected session."""
        client = UnraidClient(host, api_key, session=mock_session)  # type: ignore[arg-type]

        assert client._session is mock_session
        assert client._owns_session is False

    def test_repr_does_not_expose_api_key(self, host: str, api_key: str) -> None:
        """Test that __repr__ never includes the API key."""
        client = UnraidClient(host, api_key)
        repr_str = repr(client)

        assert api_key not in repr_str
        assert "192.168.1.100" in repr_str
        assert "UnraidClient" in repr_str

    def test_repr_with_custom_port(self, api_key: str) -> None:
        """Test __repr__ shows the HTTPS port."""
        client = UnraidClient("10.0.0.1", api_key, https_port=8443)
        repr_str = repr(client)

        assert "8443" in repr_str
        assert "x-api-key" not in repr_str


class TestClientHostParsing:
    """Tests for host parsing functionality."""

    def test_get_clean_host_without_protocol(self, api_key: str) -> None:
        """Test _normalize_host_for_request without protocol prefix."""
        client = UnraidClient("192.168.1.100", api_key)

        assert client._normalize_host_for_request() == "192.168.1.100"

    def test_get_clean_host_with_http(self, api_key: str) -> None:
        """Test _normalize_host_for_request with http:// prefix."""
        client = UnraidClient("http://192.168.1.100", api_key)

        assert client._normalize_host_for_request() == "192.168.1.100"

    def test_get_clean_host_with_https(self, api_key: str) -> None:
        """Test _normalize_host_for_request with https:// prefix."""
        client = UnraidClient("https://192.168.1.100", api_key)

        assert client._normalize_host_for_request() == "192.168.1.100"

    def test_get_clean_host_strips_trailing_slash(self, api_key: str) -> None:
        """Test _normalize_host_for_request strips trailing slashes."""
        client = UnraidClient("192.168.1.100/", api_key)

        assert client._normalize_host_for_request() == "192.168.1.100"

    def test_get_clean_host_with_full_url(self, api_key: str) -> None:
        """Test _normalize_host_for_request with full URL including path."""
        client = UnraidClient("https://myserver.myunraid.net/", api_key)

        assert client._normalize_host_for_request() == "myserver.myunraid.net"


class TestClientSessionProperty:
    """Tests for session property."""

    def test_session_property_returns_none_initially(
        self, host: str, api_key: str
    ) -> None:
        """Test session property returns None before session creation."""
        client = UnraidClient(host, api_key)

        assert client.session is None

    def test_session_property_returns_injected_session(
        self, host: str, api_key: str, mock_session: object
    ) -> None:
        """Test session property returns injected session."""
        client = UnraidClient(host, api_key, session=mock_session)  # type: ignore[arg-type]

        assert client.session is mock_session