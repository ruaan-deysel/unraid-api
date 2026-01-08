"""Tests for UnraidClient initialization and configuration."""

from __future__ import annotations

from unraid_api import UnraidClient


class TestClientInitialization:
    """Tests for client initialization."""

    def test_init_with_required_params(self, host: str, api_key: str) -> None:
        """Test client initialization with required parameters."""
        client = UnraidClient(host, api_key)

        assert client.host == host
        assert client._api_key == api_key
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

    def test_init_with_injected_session(
        self, host: str, api_key: str, mock_session: object
    ) -> None:
        """Test client initialization with injected session."""
        client = UnraidClient(host, api_key, session=mock_session)  # type: ignore[arg-type]

        assert client._session is mock_session
        assert client._owns_session is False


class TestClientHostParsing:
    """Tests for host parsing functionality."""

    def test_get_clean_host_without_protocol(self, api_key: str) -> None:
        """Test _get_clean_host without protocol prefix."""
        client = UnraidClient("192.168.1.100", api_key)

        assert client._get_clean_host() == "192.168.1.100"

    def test_get_clean_host_with_http(self, api_key: str) -> None:
        """Test _get_clean_host with http:// prefix."""
        client = UnraidClient("http://192.168.1.100", api_key)

        assert client._get_clean_host() == "192.168.1.100"

    def test_get_clean_host_with_https(self, api_key: str) -> None:
        """Test _get_clean_host with https:// prefix."""
        client = UnraidClient("https://192.168.1.100", api_key)

        assert client._get_clean_host() == "192.168.1.100"

    def test_get_clean_host_strips_trailing_slash(self, api_key: str) -> None:
        """Test _get_clean_host strips trailing slashes."""
        client = UnraidClient("192.168.1.100/", api_key)

        assert client._get_clean_host() == "192.168.1.100"

    def test_get_clean_host_with_full_url(self, api_key: str) -> None:
        """Test _get_clean_host with full URL including path."""
        client = UnraidClient("https://myserver.myunraid.net/", api_key)

        assert client._get_clean_host() == "myserver.myunraid.net"


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
