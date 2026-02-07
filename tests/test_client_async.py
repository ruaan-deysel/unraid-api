"""Tests for UnraidClient async methods using aioresponses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aioresponses import aioresponses

from unraid_api import UnraidClient
from unraid_api.exceptions import (
    UnraidAPIError,
    UnraidAuthenticationError,
    UnraidConnectionError,
    UnraidSSLError,
    UnraidTimeoutError,
)


def create_ssl_error(
    host: str = "192.168.1.100", port: int = 443
) -> aiohttp.ClientSSLError:
    """Create a mock aiohttp SSL error for testing."""
    os_error = OSError(1, "certificate verify failed")

    class MockConnectionKey:
        pass

    mock_key = MockConnectionKey()
    mock_key.ssl = True  # type: ignore[attr-defined]
    mock_key.host = host  # type: ignore[attr-defined]
    mock_key.port = port  # type: ignore[attr-defined]
    mock_key.is_ssl = True  # type: ignore[attr-defined]

    return aiohttp.ClientSSLError(mock_key, os_error)


class TestClientContextManager:
    """Tests for async context manager."""

    async def test_context_manager_creates_session(self) -> None:
        """Test that context manager creates and closes session."""
        async with UnraidClient("192.168.1.100", "test-key") as client:
            assert client.session is not None
            assert client._owns_session is True

    async def test_context_manager_closes_session(self) -> None:
        """Test that context manager closes session on exit."""
        client = UnraidClient("192.168.1.100", "test-key")
        async with client:
            session = client.session
            assert session is not None
        assert client.session is None

    async def test_injected_session_not_closed(self) -> None:
        """Test that injected session is not closed by client."""
        mock_session = MagicMock(spec=aiohttp.ClientSession)
        mock_session.close = AsyncMock()

        client = UnraidClient("192.168.1.100", "test-key", session=mock_session)
        await client.close()

        # Should not close injected session
        mock_session.close.assert_not_called()


class TestClientSessionCreation:
    """Tests for session creation."""

    async def test_create_session_with_ssl_verification(self) -> None:
        """Test session creation with SSL verification enabled."""
        client = UnraidClient("192.168.1.100", "test-key", verify_ssl=True)
        await client._create_session()

        assert client.session is not None
        await client.close()

    async def test_create_session_without_ssl_verification(self) -> None:
        """Test session creation with SSL verification disabled."""
        client = UnraidClient("192.168.1.100", "test-key", verify_ssl=False)
        await client._create_session()

        assert client.session is not None
        await client.close()

    async def test_create_session_idempotent(self) -> None:
        """Test that _create_session is idempotent."""
        client = UnraidClient("192.168.1.100", "test-key")
        await client._create_session()
        first_session = client.session

        await client._create_session()
        assert client.session is first_session

        await client.close()


class TestRedirectDiscovery:
    """Tests for URL redirect discovery."""

    async def test_discover_http_no_redirect(self) -> None:
        """Test discovery when server accepts HTTP (no SSL)."""
        with aioresponses() as m:
            # GraphQL endpoint returns a non-redirect response (GET not supported)
            m.get(
                "http://192.168.1.100/graphql",
                status=400,
                body='{"errors":[{"message":"GET not supported"}]}',
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                redirect_url, use_ssl = await client._discover_redirect_url()

                assert redirect_url is None
                assert use_ssl is False

    async def test_discover_http_no_redirect_status_200(self) -> None:
        """Test discovery when server returns 200 on HTTP (no SSL)."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=200)

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                redirect_url, use_ssl = await client._discover_redirect_url()

                assert redirect_url is None
                assert use_ssl is False

    async def test_discover_same_port_assumes_https(self) -> None:
        """Test that http_port == https_port skips probe and assumes HTTPS."""
        async with UnraidClient(
            "192.168.1.100",
            "test-key",
            http_port=4443,
            https_port=4443,
            verify_ssl=False,
        ) as client:
            redirect_url, use_ssl = await client._discover_redirect_url()

            assert redirect_url is None
            assert use_ssl is True

    async def test_discover_same_port_default_443(self) -> None:
        """Test that http_port == https_port == 443 assumes HTTPS."""
        async with UnraidClient(
            "192.168.1.100",
            "test-key",
            http_port=443,
            https_port=443,
            verify_ssl=False,
        ) as client:
            redirect_url, use_ssl = await client._discover_redirect_url()

            assert redirect_url is None
            assert use_ssl is True

    async def test_discover_nginx_400_https_port(self) -> None:
        """Test detection of nginx 400 'plain HTTP to HTTPS port' response."""
        nginx_body = (
            "<html>\n"
            "<head><title>400 The plain HTTP request was sent to HTTPS port"
            "</title></head>\n"
            "<body>\n"
            "<center><h1>400 Bad Request</h1></center>\n"
            "<center>The plain HTTP request was sent to HTTPS port</center>\n"
            "</body>\n"
            "</html>\n"
        )
        with aioresponses() as m:
            m.get(
                "http://192.168.1.100:8080/graphql",
                status=400,
                body=nginx_body,
            )

            async with UnraidClient(
                "192.168.1.100",
                "test-key",
                http_port=8080,
                https_port=4443,
                verify_ssl=False,
            ) as client:
                redirect_url, use_ssl = await client._discover_redirect_url()

                assert redirect_url == "https://192.168.1.100:8080/graphql"
                assert use_ssl is True

    async def test_discover_nginx_400_default_https_port(self) -> None:
        """Test nginx 400 on default port 443 returns URL without port suffix."""
        nginx_body = (
            "<html>\n"
            "<head><title>400 The plain HTTP request was sent to HTTPS port"
            "</title></head>\n"
            "<body>\n"
            "<center><h1>400 Bad Request</h1></center>\n"
            "<center>The plain HTTP request was sent to HTTPS port</center>\n"
            "</body>\n"
            "</html>\n"
        )
        with aioresponses() as m:
            m.get(
                "http://192.168.1.100/graphql",
                status=400,
                body=nginx_body,
            )

            async with UnraidClient(
                "192.168.1.100",
                "test-key",
                https_port=8443,
                verify_ssl=False,
            ) as client:
                redirect_url, use_ssl = await client._discover_redirect_url()

                assert redirect_url == "https://192.168.1.100/graphql"
                assert use_ssl is True

    async def test_discover_generic_400_is_http(self) -> None:
        """Test that a generic 400 (not nginx HTTPS error) means HTTP mode."""
        with aioresponses() as m:
            m.get(
                "http://192.168.1.100/graphql",
                status=400,
                body="Bad Request",
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                redirect_url, use_ssl = await client._discover_redirect_url()

                assert redirect_url is None
                assert use_ssl is False

    async def test_discover_https_redirect(self) -> None:
        """Test discovery when server redirects to HTTPS."""
        with aioresponses() as m:
            m.get(
                "http://192.168.1.100/graphql",
                status=302,
                headers={"Location": "https://192.168.1.100/graphql"},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                redirect_url, use_ssl = await client._discover_redirect_url()

                assert redirect_url == "https://192.168.1.100/graphql"
                assert use_ssl is True

    async def test_discover_https_redirect_with_port_443(self) -> None:
        """Test discovery normalizes redirect URL when port is 443."""
        with aioresponses() as m:
            m.get(
                "http://192.168.1.100/graphql",
                status=302,
                headers={"Location": "https://192.168.1.100:443/graphql"},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                redirect_url, use_ssl = await client._discover_redirect_url()

                # Port 443 should be normalized away
                assert redirect_url == "https://192.168.1.100/graphql"
                assert use_ssl is True

    async def test_discover_redirect_without_location_in_get(self) -> None:
        """Test discovery when redirect response has no Location header."""
        with aioresponses() as m:
            m.get(
                "http://192.168.1.100/graphql",
                status=302,
                # No Location header
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                redirect_url, use_ssl = await client._discover_redirect_url()

                # Falls through to "HTTP endpoint accessible"
                assert redirect_url is None
                assert use_ssl is False

    async def test_discover_redirect_to_non_https(self) -> None:
        """Test discovery when redirect goes to non-HTTPS URL."""
        with aioresponses() as m:
            m.get(
                "http://192.168.1.100/graphql",
                status=302,
                headers={"Location": "http://other-host.local/graphql"},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                redirect_url, use_ssl = await client._discover_redirect_url()

                # Non-HTTPS, non-myunraid redirect falls through
                assert redirect_url is None
                assert use_ssl is False

    async def test_discover_without_session(self) -> None:
        """Test discovery creates session if none exists."""
        client = UnraidClient("192.168.1.100", "test-key", verify_ssl=False)
        assert client._session is None

        with aioresponses() as m:
            m.get(
                "http://192.168.1.100/graphql",
                status=200,
            )

            redirect_url, use_ssl = await client._discover_redirect_url()

            assert redirect_url is None
            assert use_ssl is False
            assert client._session is not None

        await client.close()

    async def test_discover_myunraid_redirect(self) -> None:
        """Test discovery when server redirects to myunraid.net."""
        with aioresponses() as m:
            m.get(
                "http://192.168.1.100/graphql",
                status=302,
                headers={"Location": "https://myserver.myunraid.net/graphql"},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                redirect_url, use_ssl = await client._discover_redirect_url()

                assert redirect_url == "https://myserver.myunraid.net/graphql"
                assert use_ssl is True

    async def test_discover_fallback_to_https_on_error(self) -> None:
        """Test discovery falls back to HTTPS on connection error."""
        with aioresponses() as m:
            m.get(
                "http://192.168.1.100/graphql",
                exception=aiohttp.ClientError("Connection refused"),
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                redirect_url, use_ssl = await client._discover_redirect_url()

                assert redirect_url is None
                assert use_ssl is True

    async def test_discover_fallback_to_https_on_ssl_error(self) -> None:
        """Test discovery falls back to HTTPS on SSL error (doesn't raise)."""
        ssl_error = create_ssl_error()

        with aioresponses() as m:
            m.get(
                "http://192.168.1.100/graphql",
                exception=ssl_error,
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                # Discovery should catch SSL errors and fall back to HTTPS
                redirect_url, use_ssl = await client._discover_redirect_url()

                assert redirect_url is None
                assert use_ssl is True


class TestGraphQLQuery:
    """Tests for GraphQL query execution."""

    async def test_query_success(self) -> None:
        """Test successful GraphQL query."""
        with aioresponses() as m:
            # Mock redirect discovery
            m.get("http://192.168.1.100/graphql", status=400)
            # Mock GraphQL query
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"online": True}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.query("query { online }")

                assert result == {"online": True}

    async def test_query_with_variables(self) -> None:
        """Test GraphQL query with variables."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "docker": {"start": {"id": "container:123", "state": "RUNNING"}}
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                mutation = """
                    mutation StartContainer($id: PrefixedID!) {
                        docker { start(id: $id) { id state } }
                    }
                """
                result = await client.query(
                    mutation,
                    variables={"id": "container:123"},
                )

                assert result["docker"]["start"]["state"] == "RUNNING"

    async def test_query_with_graphql_errors_and_data(self) -> None:
        """Test query that returns partial data with errors."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {"array": {"state": "STARTED"}},
                    "errors": [{"message": "UPS not configured"}],
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                # Should return data despite errors
                result = await client.query("query { array { state } ups { status } }")

                assert result == {"array": {"state": "STARTED"}}

    async def test_query_with_graphql_errors_no_data(self) -> None:
        """Test query that returns only errors."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {},
                    "errors": [{"message": "Unauthorized", "path": ["query"]}],
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                with pytest.raises(UnraidAPIError) as exc_info:
                    await client.query("query { secret }")

                assert "GraphQL query failed" in str(exc_info.value)

    async def test_query_authentication_error(self) -> None:
        """Test query with authentication failure."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post("http://192.168.1.100/graphql", status=401)

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                with pytest.raises(UnraidAuthenticationError):
                    await client.query("query { online }")

    async def test_query_forbidden_error(self) -> None:
        """Test query with forbidden response."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post("http://192.168.1.100/graphql", status=403)

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                with pytest.raises(UnraidAuthenticationError):
                    await client.query("query { online }")

    async def test_query_connection_error(self) -> None:
        """Test query with connection failure."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                exception=aiohttp.ClientError("Connection refused"),
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                with pytest.raises(UnraidConnectionError):
                    await client.query("query { online }")

    async def test_query_timeout_error(self) -> None:
        """Test query with timeout."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                exception=TimeoutError("Request timed out"),
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                with pytest.raises(UnraidTimeoutError):
                    await client.query("query { online }")

    async def test_query_ssl_error(self) -> None:
        """Test query with SSL certificate error."""
        ssl_error = create_ssl_error()

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                exception=ssl_error,
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                with pytest.raises(UnraidSSLError) as exc_info:
                    await client.query("query { online }")

                assert "SSL" in str(exc_info.value)

    async def test_ssl_error_is_catchable_as_connection_error(self) -> None:
        """Test that UnraidSSLError can be caught as UnraidConnectionError."""
        ssl_error = create_ssl_error()

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                exception=ssl_error,
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                # Should be catchable as UnraidConnectionError for backwards compat
                with pytest.raises(UnraidConnectionError) as exc_info:
                    await client.query("query { online }")

                # But should actually be UnraidSSLError
                assert isinstance(exc_info.value, UnraidSSLError)
                assert isinstance(exc_info.value, UnraidSSLError)


class TestMutate:
    """Tests for GraphQL mutation execution."""

    async def test_mutate_calls_query(self) -> None:
        """Test that mutate delegates to query."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {"docker": {"start": {"id": "c:1", "state": "RUNNING"}}}
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.mutate(
                    "mutation { docker { start(id: $id) { id state } } }",
                    {"id": "c:1"},
                )

                assert result["docker"]["start"]["state"] == "RUNNING"


class TestConnectionMethods:
    """Tests for connection-related methods."""

    async def test_test_connection_success(self) -> None:
        """Test successful connection test."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"online": True}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.test_connection()

                assert result is True

    async def test_test_connection_offline(self) -> None:
        """Test connection test when server reports offline."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"online": False}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.test_connection()

                assert result is False

    async def test_get_version(self) -> None:
        """Test getting version information."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
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
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_version()

                assert result == {"unraid": "7.2.0", "api": "4.21.0"}


class TestContainerMethods:
    """Tests for Docker container methods."""

    async def test_start_container(self) -> None:
        """Test starting a Docker container."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "docker": {
                            "start": {
                                "id": "container:plex",
                                "state": "RUNNING",
                                "status": "Up 5 seconds",
                            }
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.start_container("container:plex")

                assert result["docker"]["start"]["state"] == "RUNNING"

    async def test_stop_container(self) -> None:
        """Test stopping a Docker container."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "docker": {
                            "stop": {
                                "id": "container:plex",
                                "state": "EXITED",
                                "status": "Exited (0)",
                            }
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.stop_container("container:plex")

                assert result["docker"]["stop"]["state"] == "EXITED"


class TestVmMethods:
    """Tests for VM methods."""

    async def test_start_vm(self) -> None:
        """Test starting a VM."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"vm": {"start": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.start_vm("vm:windows")

                assert result["vm"]["start"] is True

    async def test_stop_vm(self) -> None:
        """Test stopping a VM."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"vm": {"stop": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.stop_vm("vm:windows")

                assert result["vm"]["stop"] is True


class TestArrayMethods:
    """Tests for array control methods."""

    async def test_start_array(self) -> None:
        """Test starting the array."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "array": {"setState": {"id": "array:1", "state": "STARTED"}}
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.start_array()

                assert result["array"]["setState"]["state"] == "STARTED"

    async def test_stop_array(self) -> None:
        """Test stopping the array."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "array": {"setState": {"id": "array:1", "state": "STOPPED"}}
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.stop_array()

                assert result["array"]["setState"]["state"] == "STOPPED"


class TestParityMethods:
    """Tests for parity check methods."""

    async def test_start_parity_check(self) -> None:
        """Test starting parity check."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"parityCheck": {"start": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.start_parity_check()

                assert result["parityCheck"]["start"] is True

    async def test_start_parity_check_with_correction(self) -> None:
        """Test starting parity check with correction enabled."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"parityCheck": {"start": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.start_parity_check(correct=True)

                assert result["parityCheck"]["start"] is True

    async def test_pause_parity_check(self) -> None:
        """Test pausing parity check."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"parityCheck": {"pause": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.pause_parity_check()

                assert result["parityCheck"]["pause"] is True

    async def test_resume_parity_check(self) -> None:
        """Test resuming parity check."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"parityCheck": {"resume": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.resume_parity_check()

                assert result["parityCheck"]["resume"] is True

    async def test_cancel_parity_check(self) -> None:
        """Test canceling parity check."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"parityCheck": {"cancel": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.cancel_parity_check()

                assert result["parityCheck"]["cancel"] is True


class TestDiskSpinMethods:
    """Tests for disk spin control methods."""

    async def test_spin_up_disk(self) -> None:
        """Test spinning up a disk."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "array": {
                            "mountArrayDisk": {"id": "disk:1", "isSpinning": True}
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.spin_up_disk("disk:1")

                assert result["array"]["mountArrayDisk"]["isSpinning"] is True

    async def test_spin_down_disk(self) -> None:
        """Test spinning down a disk."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "array": {
                            "unmountArrayDisk": {"id": "disk:1", "isSpinning": False}
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.spin_down_disk("disk:1")

                assert result["array"]["unmountArrayDisk"]["isSpinning"] is False


class TestRedirectFollowing:
    """Tests for redirect following during requests."""

    async def test_follows_redirect_on_post(self) -> None:
        """Test that POST requests follow redirects."""
        with aioresponses() as m:
            # Discovery finds HTTP works
            m.get("http://192.168.1.100/graphql", status=400)
            # First POST gets redirect
            m.post(
                "http://192.168.1.100/graphql",
                status=302,
                headers={"Location": "https://192.168.1.100/graphql"},
            )
            # Follow redirect
            m.post(
                "https://192.168.1.100/graphql",
                payload={"data": {"online": True}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.query("query { online }")

                assert result == {"online": True}


class TestAdditionalContainerMethods:
    """Tests for additional Docker container methods."""

    async def test_pause_container(self) -> None:
        """Test pausing a container."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "docker": {
                            "pause": {
                                "id": "container:abc123",
                                "state": "paused",
                                "status": "Paused",
                            }
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.pause_container("container:abc123")

                assert result["docker"]["pause"]["state"] == "paused"

    async def test_unpause_container(self) -> None:
        """Test unpausing a container."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "docker": {
                            "unpause": {
                                "id": "container:abc123",
                                "state": "running",
                                "status": "Up 5 days",
                            }
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.unpause_container("container:abc123")

                assert result["docker"]["unpause"]["state"] == "running"

    async def test_update_container(self) -> None:
        """Test updating a container."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "docker": {
                            "updateContainer": {
                                "id": "container:abc123",
                                "names": ["/plex"],
                                "image": "plex:latest",
                                "state": "running",
                            }
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.update_container("container:abc123")

                assert result["docker"]["updateContainer"]["image"] == "plex:latest"

    async def test_get_containers(self) -> None:
        """Test getting all containers."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "docker": {
                            "containers": [
                                {
                                    "id": "container:abc123",
                                    "names": ["/plex"],
                                    "image": "plex:latest",
                                    "state": "running",
                                    "status": "Up 5 days",
                                    "autoStart": True,
                                    "ports": [],
                                    "isUpdateAvailable": False,
                                    "isOrphaned": False,
                                    "webUiUrl": "http://192.168.1.100:32400",
                                    "iconUrl": "/plugins/plex/icon.png",
                                },
                            ]
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_containers()

                assert len(result) == 1
                assert result[0]["id"] == "container:abc123"
                assert result[0]["state"] == "running"


class TestAdditionalVmMethods:
    """Tests for additional VM methods."""

    async def test_pause_vm(self) -> None:
        """Test pausing a VM."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"vm": {"pause": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.pause_vm("vm:windows10")

                assert result["vm"]["pause"] is True

    async def test_resume_vm(self) -> None:
        """Test resuming a VM."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"vm": {"resume": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.resume_vm("vm:windows10")

                assert result["vm"]["resume"] is True

    async def test_force_stop_vm(self) -> None:
        """Test force stopping a VM."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"vm": {"forceStop": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.force_stop_vm("vm:windows10")

                assert result["vm"]["forceStop"] is True

    async def test_reboot_vm(self) -> None:
        """Test rebooting a VM."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"vm": {"reboot": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.reboot_vm("vm:windows10")

                assert result["vm"]["reboot"] is True

    async def test_get_vms(self) -> None:
        """Test getting all VMs."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "vms": {
                            "domains": [
                                {
                                    "id": "vm:windows10",
                                    "name": "Windows 10",
                                    "state": "running",
                                },
                            ]
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_vms()

                assert len(result) == 1
                assert result[0]["name"] == "Windows 10"


class TestMetricsMethods:
    """Tests for system metrics methods."""

    async def test_get_metrics(self) -> None:
        """Test getting system metrics."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "metrics": {
                            "cpu": {
                                "percentTotal": 15.5,
                                "cpus": [
                                    {
                                        "percentTotal": 20.0,
                                        "percentUser": 10.0,
                                        "percentSystem": 5.0,
                                        "percentIdle": 80.0,
                                    }
                                ],
                            },
                            "memory": {
                                "total": 17179869184,
                                "used": 8589934592,
                                "free": 4294967296,
                                "available": 8589934592,
                                "percentTotal": 50.0,
                                "swapTotal": 0,
                                "swapUsed": 0,
                                "swapFree": 0,
                                "percentSwapTotal": 0.0,
                            },
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_metrics()

                assert result["cpu"]["percentTotal"] == 15.5
                assert result["memory"]["percentTotal"] == 50.0

    async def test_get_system_info(self) -> None:
        """Test getting system info."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "info": {
                            "time": "2024-01-15T12:00:00Z",
                            "os": {
                                "hostname": "Tower",
                                "uptime": 1000000,
                                "kernel": "6.1.38-Unraid",
                                "platform": "linux",
                                "distro": "Unraid",
                                "arch": "x64",
                            },
                            "cpu": {
                                "manufacturer": "Intel",
                                "brand": "Core i7-12700K",
                                "cores": 12,
                                "threads": 20,
                                "speed": 3.60,
                            },
                            "memory": {"layout": []},
                            "versions": {
                                "core": {
                                    "unraid": "7.1.4",
                                    "api": "4.29.2",
                                    "kernel": "6.1.38-Unraid",
                                },
                                "packages": {
                                    "docker": "24.0.7",
                                    "openssl": "3.1.4",
                                    "node": "18.19.0",
                                },
                            },
                            "baseboard": {
                                "manufacturer": "ASUS",
                                "model": "Z690",
                                "memMax": 128,
                                "memSlots": 4,
                            },
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_system_info()

                assert result["os"]["hostname"] == "Tower"
                assert result["versions"]["core"]["unraid"] == "7.1.4"


class TestArrayStatusMethod:
    """Tests for array status method."""

    async def test_get_array_status(self) -> None:
        """Test getting comprehensive array status."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "array": {
                            "state": "STARTED",
                            "capacity": {
                                "kilobytes": {
                                    "free": 1000000,
                                    "used": 500000,
                                    "total": 1500000,
                                },
                                "disks": {"free": 5, "used": 3, "total": 8},
                            },
                            "parityCheckStatus": {
                                "status": "IDLE",
                                "progress": 0,
                                "running": False,
                                "paused": False,
                                "errors": 0,
                                "speed": 0,
                            },
                            "boot": {
                                "id": "boot:0",
                                "name": "boot",
                                "device": "sda",
                                "size": 32000000,
                                "temp": None,
                                "type": "Flash",
                            },
                            "parities": [
                                {
                                    "id": "parity:0",
                                    "name": "Parity",
                                    "device": "sdb",
                                    "size": 4000000000,
                                    "status": "DISK_OK",
                                    "type": "Parity",
                                    "temp": 35,
                                    "numReads": 1000,
                                    "numWrites": 500,
                                    "numErrors": 0,
                                }
                            ],
                            "disks": [
                                {
                                    "id": "disk:1",
                                    "name": "Disk 1",
                                    "device": "sdc",
                                    "size": 4000000000,
                                    "status": "DISK_OK",
                                    "type": "Data",
                                    "temp": 32,
                                    "fsSize": 3900000000,
                                    "fsFree": 1000000000,
                                    "fsUsed": 2900000000,
                                    "numReads": 5000,
                                    "numWrites": 3000,
                                    "numErrors": 0,
                                    "isSpinning": True,
                                }
                            ],
                            "caches": [],
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_array_status()

                assert result["state"] == "STARTED"
                assert len(result["disks"]) == 1
                assert result["disks"][0]["name"] == "Disk 1"


class TestSharesMethod:
    """Tests for shares method."""

    async def test_get_shares(self) -> None:
        """Test getting all shares."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "shares": [
                            {
                                "id": "share:appdata",
                                "name": "appdata",
                                "free": 1000000,
                                "used": 500000,
                                "size": 1500000,
                                "cache": "yes",
                                "comment": "Application data",
                                "include": "",
                                "exclude": "",
                            },
                            {
                                "id": "share:media",
                                "name": "media",
                                "free": 2000000,
                                "used": 8000000,
                                "size": 10000000,
                                "cache": "no",
                                "comment": "Media files",
                                "include": "",
                                "exclude": "",
                            },
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_shares()

                assert len(result) == 2
                assert result[0]["name"] == "appdata"
                assert result[1]["name"] == "media"


class TestUpsMethod:
    """Tests for UPS method."""

    async def test_get_ups_status(self) -> None:
        """Test getting UPS status."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "upsDevices": [
                            {
                                "id": "ups:0",
                                "name": "CyberPower CP1500",
                                "model": "CP1500PFCLCD",
                                "status": "OL",
                                "battery": {
                                    "chargeLevel": 100,
                                    "estimatedRuntime": 1800,
                                    "health": "GOOD",
                                },
                                "power": {
                                    "inputVoltage": 120.0,
                                    "outputVoltage": 120.0,
                                    "loadPercentage": 25.0,
                                },
                            }
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_ups_status()

                assert len(result) == 1
                assert result[0]["name"] == "CyberPower CP1500"
                assert result[0]["battery"]["chargeLevel"] == 100


class TestNotificationsMethod:
    """Tests for notifications method."""

    async def test_get_notifications(self) -> None:
        """Test getting notifications."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "notifications": {
                            "overview": {
                                "unread": {
                                    "info": 5,
                                    "warning": 2,
                                    "alert": 0,
                                    "total": 7,
                                },
                                "archive": {
                                    "info": 100,
                                    "warning": 20,
                                    "alert": 5,
                                    "total": 125,
                                },
                            },
                            "list": [
                                {
                                    "id": "notif:1",
                                    "title": "Array Started",
                                    "subject": "Array",
                                    "description": "Array started",
                                    "importance": "INFO",
                                    "timestamp": "2024-01-15T12:00:00Z",
                                },
                                {
                                    "id": "notif:2",
                                    "title": "Disk Warning",
                                    "subject": "Disk 1",
                                    "description": "Disk 1 temperature is high",
                                    "importance": "WARNING",
                                    "timestamp": "2024-01-15T11:00:00Z",
                                },
                            ],
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_notifications()

                assert result["overview"]["unread"]["total"] == 7
                assert len(result["list"]) == 2
                assert result["list"][0]["title"] == "Array Started"

    async def test_get_notifications_with_params(self) -> None:
        """Test getting notifications with parameters."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "notifications": {
                            "overview": {
                                "unread": {
                                    "info": 0,
                                    "warning": 0,
                                    "alert": 0,
                                    "total": 0,
                                },
                                "archive": {
                                    "info": 100,
                                    "warning": 20,
                                    "alert": 5,
                                    "total": 125,
                                },
                            },
                            "list": [],
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_notifications(
                    notification_type="ARCHIVE", limit=10, offset=0
                )

                assert result["overview"]["archive"]["total"] == 125


class TestEdgeCases:
    """Tests for edge cases and defensive code paths."""

    async def test_redirect_without_location_header(self) -> None:
        """Test handling of redirect response without Location header."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                status=302,
                # No Location header
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                with pytest.raises(UnraidConnectionError) as exc_info:
                    await client.query("query { online }")
                assert "Redirect" in str(exc_info.value)
                assert "without Location header" in str(exc_info.value)

    async def test_graphql_error_with_path(self) -> None:
        """Test GraphQL error with path information."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": None,
                    "errors": [
                        {
                            "message": "Cannot query field 'invalid'",
                            "path": ["query", "invalid"],
                        }
                    ],
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                with pytest.raises(UnraidAPIError) as exc_info:
                    await client.query("query { invalid }")
                assert "Cannot query field" in str(exc_info.value)

    async def test_use_https_when_discovery_fails(self) -> None:
        """Test that HTTPS is used when HTTP discovery fails."""
        with aioresponses() as m:
            # HTTP fails completely
            m.get(
                "http://192.168.1.100/graphql",
                exception=aiohttp.ClientError("Connection refused"),
            )
            # HTTPS works
            m.post(
                "https://192.168.1.100/graphql",
                payload={"data": {"online": True}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.query("query { online }")
                assert result == {"online": True}

    async def test_custom_https_port_in_url(self) -> None:
        """Test that custom HTTPS port is included in URL."""
        with aioresponses() as m:
            # HTTP fails
            m.get(
                "http://192.168.1.100/graphql",
                exception=aiohttp.ClientError("Connection refused"),
            )
            # HTTPS on custom port works
            m.post(
                "https://192.168.1.100:8443/graphql",
                payload={"data": {"online": True}},
            )

            async with UnraidClient(
                "192.168.1.100",
                "test-key",
                https_port=8443,
                verify_ssl=False,
            ) as client:
                result = await client.query("query { online }")
                assert result == {"online": True}

    async def test_discover_raises_if_session_creation_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _discover_redirect_url raises if session stays None."""
        client = UnraidClient("192.168.1.100", "test-key", verify_ssl=False)

        monkeypatch.setattr(client, "_create_session", AsyncMock())

        with pytest.raises(
            UnraidConnectionError, match="Failed to create HTTP session"
        ):
            await client._discover_redirect_url()

    async def test_make_request_raises_if_session_creation_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _make_request raises if session stays None."""
        client = UnraidClient("192.168.1.100", "test-key", verify_ssl=False)

        monkeypatch.setattr(client, "_create_session", AsyncMock())

        with pytest.raises(
            UnraidConnectionError, match="Failed to create HTTP session"
        ):
            await client._make_request({"query": "query { online }"})

    async def test_make_request_skips_discovery_when_url_resolved(self) -> None:
        """Test _make_request skips discovery when URL already resolved."""
        with aioresponses() as m:
            # Only mock the POST, no GET needed since URL is pre-resolved
            m.post(
                "https://192.168.1.100/graphql",
                payload={"data": {"online": True}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                # Pre-set resolved URL to skip discovery
                client._resolved_url = "https://192.168.1.100/graphql"
                result = await client.query("query { online }")

                assert result == {"online": True}

    async def test_make_request_creates_session_if_none(self) -> None:
        """Test that _make_request creates session if none exists."""
        client = UnraidClient("192.168.1.100", "test-key", verify_ssl=False)
        assert client._session is None

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=200)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"online": True}},
            )

            result = await client.query("query { online }")
            assert result == {"online": True}
            assert client._session is not None

        await client.close()

    async def test_make_request_uses_redirect_url_from_discovery(self) -> None:
        """Test that _make_request uses redirect URL from discovery."""
        with aioresponses() as m:
            # Redirect to myunraid.net (Strict mode)
            m.get(
                "http://192.168.1.100/graphql",
                status=302,
                headers={"Location": "https://myserver.myunraid.net/graphql"},
            )
            m.post(
                "https://myserver.myunraid.net/graphql",
                payload={"data": {"online": True}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.query("query { online }")

                assert result == {"online": True}
                assert client._resolved_url == "https://myserver.myunraid.net/graphql"

    async def test_query_with_non_dict_error_items(self) -> None:
        """Test query handles non-dict error items in GraphQL response."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {},
                    "errors": ["Simple string error", "Another error"],
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                with pytest.raises(UnraidAPIError) as exc_info:
                    await client.query("query { invalid }")

                assert "Simple string error" in str(exc_info.value)

    async def test_partial_failure_returns_data(self) -> None:
        """Test that partial failures return data with errors logged."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {"online": True, "someField": None},
                    "errors": [
                        {"message": "someField is deprecated"},
                    ],
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.query("query { online someField }")
                # Data is returned despite errors
                assert result["online"] is True


class TestRemoveContainerMethod:
    """Tests for remove container method."""

    async def test_remove_container(self) -> None:
        """Test removing a container."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"docker": {"removeContainer": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.remove_container("container:abc123")

                assert result["docker"]["removeContainer"] is True

    async def test_remove_container_with_image(self) -> None:
        """Test removing a container with its image."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"docker": {"removeContainer": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.remove_container(
                    "container:abc123", with_image=True
                )

                assert result["docker"]["removeContainer"] is True


class TestDisksMethod:
    """Tests for physical disks method."""

    async def test_get_disks(self) -> None:
        """Test getting physical disks."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "disks": [
                            {
                                "id": "disk:sda",
                                "device": "/dev/sda",
                                "name": "Samsung SSD 870 EVO",
                                "vendor": "Samsung",
                                "size": 500107862016,
                                "type": "SSD",
                                "interfaceType": "SATA",
                                "smartStatus": "OK",
                                "temperature": 32,
                                "isSpinning": False,
                                "partitions": [
                                    {
                                        "name": "sda1",
                                        "fsType": "XFS",
                                        "size": 500000000000,
                                    }
                                ],
                            }
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_disks()

                assert len(result) == 1
                assert result[0]["name"] == "Samsung SSD 870 EVO"


class TestParityHistoryMethod:
    """Tests for parity history method."""

    async def test_get_parity_history(self) -> None:
        """Test getting parity check history."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "parityHistory": [
                            {
                                "date": "2024-01-15",
                                "duration": 36000,
                                "speed": 150000000,
                                "status": "COMPLETED",
                                "errors": 0,
                            },
                            {
                                "date": "2024-01-01",
                                "duration": 35500,
                                "speed": 155000000,
                                "status": "COMPLETED",
                                "errors": 0,
                            },
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_parity_history()

                assert len(result) == 2
                assert result[0]["status"] == "COMPLETED"
                assert result[0]["errors"] == 0


class TestGetServerInfoMethod:
    """Tests for get_server_info method."""

    async def test_get_server_info(self) -> None:
        """Test getting server info returns ServerInfo model."""
        from unraid_api.models import ServerInfo

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "info": {
                            "system": {
                                "uuid": "abc123-def456",
                                "manufacturer": "Dell Inc.",
                                "model": "PowerEdge R730",
                                "serial": "SYS123",
                            },
                            "baseboard": {
                                "manufacturer": "Dell",
                                "model": "0HFG24",
                                "serial": "BB456",
                            },
                            "os": {
                                "hostname": "Tower",
                                "distro": "Unraid",
                                "release": "7.2.0",
                                "kernel": "6.1.38-Unraid",
                                "arch": "x64",
                            },
                            "cpu": {
                                "manufacturer": "Intel",
                                "brand": "Intel Xeon E5-2680",
                                "cores": 12,
                                "threads": 24,
                            },
                            "versions": {
                                "core": {
                                    "unraid": "7.2.0",
                                    "api": "4.29.2",
                                }
                            },
                        },
                        "server": {
                            "lanip": "192.168.1.100",
                            "localurl": "http://192.168.1.100",
                            "remoteurl": "https://myserver.myunraid.net",
                        },
                        "registration": {
                            "type": "Pro",
                            "state": "valid",
                        },
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_server_info()

                # Check it returns a ServerInfo instance
                assert isinstance(result, ServerInfo)

                # Verify fields
                assert result.uuid == "abc123-def456"
                assert result.hostname == "Tower"
                assert result.manufacturer == "Lime Technology"
                assert result.model == "Unraid 7.2.0"
                assert result.sw_version == "7.2.0"
                assert result.hw_version == "6.1.38-Unraid"
                assert result.serial_number == "SYS123"
                assert result.hw_manufacturer == "Dell Inc."
                assert result.hw_model == "PowerEdge R730"
                assert result.api_version == "4.29.2"
                assert result.lan_ip == "192.168.1.100"
                assert result.local_url == "http://192.168.1.100"
                assert result.remote_url == "https://myserver.myunraid.net"
                assert result.license_type == "Pro"
                assert result.license_state == "valid"
                assert result.cpu_brand == "Intel Xeon E5-2680"
                assert result.cpu_cores == 12
                assert result.cpu_threads == 24

    async def test_get_server_info_with_baseboard_fallback(self) -> None:
        """Test server info falls back to baseboard when system info missing."""
        from unraid_api.models import ServerInfo

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "info": {
                            "system": {
                                "uuid": "abc123",
                                "manufacturer": None,
                                "model": None,
                                "serial": None,
                            },
                            "baseboard": {
                                "manufacturer": "ASUS",
                                "model": "Z690",
                                "serial": "BBSERIAL123",
                            },
                            "os": {
                                "hostname": "MyTower",
                                "distro": "Unraid",
                                "release": "7.1.4",
                                "kernel": "6.1.38-Unraid",
                                "arch": "x64",
                            },
                            "cpu": {
                                "brand": "Intel Core i7-12700K",
                                "cores": 12,
                                "threads": 20,
                            },
                            "versions": {
                                "core": {
                                    "unraid": "7.1.4",
                                    "api": "4.21.0",
                                }
                            },
                        },
                        "server": {
                            "lanip": "192.168.1.50",
                        },
                        "registration": {
                            "type": "Basic",
                            "state": "valid",
                        },
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_server_info()

                assert isinstance(result, ServerInfo)
                assert result.hw_manufacturer == "ASUS"
                assert result.hw_model == "Z690"
                assert result.serial_number == "BBSERIAL123"

    async def test_get_server_info_minimal_response(self) -> None:
        """Test server info with minimal data in response."""
        from unraid_api.models import ServerInfo

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "info": {
                            "system": {"uuid": "min-uuid"},
                            "baseboard": {},
                            "os": {"hostname": "MinimalServer"},
                            "cpu": {},
                            "versions": {
                                "core": {
                                    "unraid": "7.0.0",
                                }
                            },
                        },
                        "server": {},
                        "registration": {},
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_server_info()

                assert isinstance(result, ServerInfo)
                assert result.uuid == "min-uuid"
                assert result.hostname == "MinimalServer"
                assert result.model == "Unraid 7.0.0"
                assert result.lan_ip is None
                assert result.license_type is None


class TestGetSystemMetricsMethod:
    """Tests for get_system_metrics method (returns SystemMetrics model)."""

    async def test_get_system_metrics(self) -> None:
        """Test getting system metrics returns SystemMetrics model."""
        from unraid_api.models import SystemMetrics

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "metrics": {
                            "cpu": {"percentTotal": 25.5},
                            "memory": {
                                "total": 34359738368,
                                "used": 17179869184,
                                "free": 17179869184,
                                "available": 25769803776,
                                "percentTotal": 50.0,
                                "swapTotal": 8589934592,
                                "swapUsed": 0,
                                "percentSwapTotal": 0.0,
                            },
                        },
                        "info": {
                            "os": {"uptime": "2024-01-15T10:30:00Z"},
                        },
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_system_metrics()

                assert isinstance(result, SystemMetrics)
                assert result.cpu_percent == 25.5
                assert result.memory_percent == 50.0
                assert result.memory_total == 34359738368
                assert result.memory_used == 17179869184
                assert result.memory_available == 25769803776
                assert result.swap_percent == 0.0
                assert result.uptime is not None

    async def test_get_system_metrics_minimal_response(self) -> None:
        """Test system metrics with minimal response data."""
        from unraid_api.models import SystemMetrics

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "metrics": {
                            "cpu": {"percentTotal": 10.0},
                            "memory": {"percentTotal": 30.0},
                        },
                        "info": {"os": {}},
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_system_metrics()

                assert isinstance(result, SystemMetrics)
                assert result.cpu_percent == 10.0
                assert result.memory_percent == 30.0
                assert result.uptime is None


class TestTypedGetContainersMethod:
    """Tests for typed_get_containers method (returns list[DockerContainer])."""

    async def test_typed_get_containers(self) -> None:
        """Test getting containers returns list of DockerContainer models."""
        from unraid_api.models import DockerContainer

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "docker": {
                            "containers": [
                                {
                                    "id": "container:abc123",
                                    "names": ["/plex"],
                                    "image": "plexinc/pms-docker",
                                    "state": "running",
                                    "status": "Up 5 days",
                                    "autoStart": True,
                                    "ports": [
                                        {
                                            "ip": "192.168.1.100",
                                            "privatePort": 32400,
                                            "publicPort": 32400,
                                            "type": "tcp",
                                        }
                                    ],
                                },
                                {
                                    "id": "container:def456",
                                    "names": ["/sonarr"],
                                    "image": "linuxserver/sonarr",
                                    "state": "stopped",
                                    "status": "Exited (0) 2 hours ago",
                                    "autoStart": False,
                                    "ports": [],
                                },
                            ]
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_containers()

                assert isinstance(result, list)
                assert len(result) == 2
                assert all(isinstance(c, DockerContainer) for c in result)
                assert result[0].id == "container:abc123"
                assert result[0].name == "plex"
                assert result[0].state == "running"
                assert result[0].image == "plexinc/pms-docker"
                assert len(result[0].ports) == 1
                assert result[1].id == "container:def456"
                assert result[1].name == "sonarr"
                assert result[1].state == "stopped"

    async def test_typed_get_containers_empty(self) -> None:
        """Test getting containers returns empty list when none exist."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"docker": {"containers": []}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_containers()

                assert isinstance(result, list)
                assert len(result) == 0


class TestTypedGetVmsMethod:
    """Tests for typed_get_vms method (returns list[VmDomain])."""

    async def test_typed_get_vms(self) -> None:
        """Test getting VMs returns list of VmDomain models."""
        from unraid_api.models import VmDomain

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "vms": {
                            "domains": [
                                {
                                    "id": "vm:win10",
                                    "name": "Windows 10",
                                    "state": "RUNNING",
                                },
                                {
                                    "id": "vm:ubuntu",
                                    "name": "Ubuntu Server",
                                    "state": "SHUTOFF",
                                },
                            ]
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_vms()

                assert isinstance(result, list)
                assert len(result) == 2
                assert all(isinstance(vm, VmDomain) for vm in result)
                assert result[0].id == "vm:win10"
                assert result[0].name == "Windows 10"
                assert result[0].state == "RUNNING"
                assert result[1].id == "vm:ubuntu"
                assert result[1].state == "SHUTOFF"

    async def test_typed_get_vms_empty(self) -> None:
        """Test getting VMs returns empty list when none exist."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"vms": {"domains": []}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_vms()

                assert isinstance(result, list)
                assert len(result) == 0


class TestTypedGetUpsDevicesMethod:
    """Tests for typed_get_ups_devices method (returns list[UPSDevice])."""

    async def test_typed_get_ups_devices(self) -> None:
        """Test getting UPS devices returns list of UPSDevice models."""
        from unraid_api.models import UPSDevice

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "upsDevices": [
                            {
                                "id": "ups:cyberpower",
                                "name": "CyberPower UPS",
                                "model": "CP1500AVRLCD",
                                "status": "OL",
                                "battery": {
                                    "chargeLevel": 100,
                                    "estimatedRuntime": 3600,
                                },
                                "power": {
                                    "inputVoltage": 120.5,
                                    "outputVoltage": 120.0,
                                    "loadPercentage": 25.0,
                                },
                            }
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_ups_devices()

                assert isinstance(result, list)
                assert len(result) == 1
                assert isinstance(result[0], UPSDevice)
                assert result[0].id == "ups:cyberpower"
                assert result[0].name == "CyberPower UPS"
                assert result[0].status == "OL"
                assert result[0].battery.chargeLevel == 100
                assert result[0].power.loadPercentage == 25.0

    async def test_typed_get_ups_devices_empty(self) -> None:
        """Test getting UPS devices returns empty list when none exist."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"upsDevices": []}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_ups_devices()

                assert isinstance(result, list)
                assert len(result) == 0


class TestTypedGetArrayMethod:
    """Tests for typed_get_array method (returns UnraidArray model)."""

    async def test_typed_get_array(self) -> None:
        """Test getting array returns UnraidArray model."""
        from unraid_api.models import UnraidArray

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "array": {
                            "state": "STARTED",
                            "capacity": {
                                "kilobytes": {
                                    "total": 10000000000,
                                    "used": 4000000000,
                                    "free": 6000000000,
                                }
                            },
                            "parityCheckStatus": {
                                "status": "IDLE",
                                "progress": 0,
                                "running": False,
                                "errors": 0,
                            },
                            "boot": {
                                "id": "disk:boot",
                                "name": "flash",
                                "device": "sdc",
                                "size": 32000000,
                            },
                            "parities": [
                                {
                                    "id": "disk:parity1",
                                    "idx": 0,
                                    "name": "Parity",
                                    "device": "sda",
                                    "size": 4000000000,
                                    "status": "DISK_OK",
                                    "temp": 35,
                                    "isSpinning": True,
                                }
                            ],
                            "disks": [
                                {
                                    "id": "disk:disk1",
                                    "idx": 1,
                                    "name": "Disk 1",
                                    "device": "sdb",
                                    "size": 4000000000,
                                    "status": "DISK_OK",
                                    "temp": 38,
                                    "isSpinning": True,
                                    "fsSize": 3900000000,
                                    "fsUsed": 2000000000,
                                    "fsFree": 1900000000,
                                }
                            ],
                            "caches": [],
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_array()

                assert isinstance(result, UnraidArray)
                assert result.state == "STARTED"
                assert result.capacity.kilobytes.total == 10000000000
                assert len(result.parities) == 1
                assert result.parities[0].id == "disk:parity1"
                assert result.parities[0].temp == 35
                assert len(result.disks) == 1
                assert result.disks[0].name == "Disk 1"
                assert result.boot is not None
                assert result.boot.name == "flash"


class TestTypedGetSharesMethod:
    """Tests for typed_get_shares method (returns list[Share])."""

    async def test_typed_get_shares(self) -> None:
        """Test getting shares returns list of Share models."""
        from unraid_api.models import Share

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "shares": [
                            {
                                "id": "share:appdata",
                                "name": "appdata",
                                "size": 0,
                                "used": 50000000,
                                "free": 100000000,
                            },
                            {
                                "id": "share:media",
                                "name": "media",
                                "size": 500000000,
                                "used": 300000000,
                                "free": 200000000,
                            },
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_shares()

                assert isinstance(result, list)
                assert len(result) == 2
                assert all(isinstance(s, Share) for s in result)
                assert result[0].id == "share:appdata"
                assert result[0].name == "appdata"
                assert result[1].id == "share:media"
                assert result[1].size == 500000000

    async def test_typed_get_shares_empty(self) -> None:
        """Test getting shares returns empty list when none exist."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"shares": []}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_shares()

                assert isinstance(result, list)
                assert len(result) == 0


class TestGetNotificationOverviewMethod:
    """Tests for get_notification_overview method (returns NotificationOverview)."""

    async def test_get_notification_overview(self) -> None:
        """Test getting notification overview returns NotificationOverview model."""
        from unraid_api.models import NotificationOverview

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "notifications": {
                            "overview": {
                                "unread": {
                                    "info": 3,
                                    "warning": 1,
                                    "alert": 0,
                                    "total": 4,
                                },
                                "archive": {
                                    "info": 50,
                                    "warning": 10,
                                    "alert": 2,
                                    "total": 62,
                                },
                            }
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_notification_overview()

                assert isinstance(result, NotificationOverview)
                assert result.unread.info == 3
                assert result.unread.warning == 1
                assert result.unread.alert == 0
                assert result.unread.total == 4
                assert result.archive.total == 62

    async def test_get_notification_overview_empty(self) -> None:
        """Test notification overview with no notifications."""
        from unraid_api.models import NotificationOverview

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "notifications": {
                            "overview": {
                                "unread": {
                                    "info": 0,
                                    "warning": 0,
                                    "alert": 0,
                                    "total": 0,
                                },
                                "archive": {
                                    "info": 0,
                                    "warning": 0,
                                    "alert": 0,
                                    "total": 0,
                                },
                            }
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_notification_overview()

                assert isinstance(result, NotificationOverview)
                assert result.unread.total == 0
                assert result.archive.total == 0


class TestGetRegistrationMethod:
    """Tests for get_registration and typed_get_registration methods."""

    async def test_get_registration(self) -> None:
        """Test getting registration information."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "registration": {
                            "id": "registration:1",
                            "type": "Pro",
                            "state": "VALID",
                            "expiration": "2025-12-31",
                            "updateExpiration": "2025-12-31",
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_registration()

                assert result["id"] == "registration:1"
                assert result["type"] == "Pro"
                assert result["state"] == "VALID"

    async def test_typed_get_registration(self) -> None:
        """Test getting registration as Pydantic model."""
        from unraid_api.models import Registration

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "registration": {
                            "id": "registration:1",
                            "type": "Pro",
                            "state": "VALID",
                            "expiration": None,
                            "updateExpiration": None,
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_registration()

                assert isinstance(result, Registration)
                assert result.id == "registration:1"
                assert result.type == "Pro"
                assert result.state == "VALID"


class TestGetVarsMethod:
    """Tests for get_vars method."""

    async def test_get_vars(self) -> None:
        """Test getting system variables."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "vars": {
                            "id": "vars:1",
                            "version": "7.2.3",
                            "name": "Cube",
                            "timeZone": "UTC",
                            "mdNumDisks": 4,
                            "mdState": "STARTED",
                            "fsState": "Running",
                            "shareCount": 10,
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_vars()

                assert result["id"] == "vars:1"
                assert result["version"] == "7.2.3"
                assert result["name"] == "Cube"
                assert result["timeZone"] == "UTC"
                assert result["mdNumDisks"] == 4

    async def test_typed_get_vars(self) -> None:
        """Test getting system variables as Pydantic model."""
        from unraid_api.models import Vars

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "vars": {
                            "id": "vars:1",
                            "version": "7.2.3",
                            "name": "Cube",
                            "timeZone": "America/New_York",
                            "mdState": "STARTED",
                            "shareCount": 15,
                            "shareSmbEnabled": True,
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_vars()

                assert isinstance(result, Vars)
                assert result.name == "Cube"
                assert result.time_zone == "America/New_York"
                assert result.md_state == "STARTED"
                assert result.share_count == 15
                assert result.share_smb_enabled is True


class TestGetServicesMethod:
    """Tests for get_services and typed_get_services methods."""

    async def test_get_services(self) -> None:
        """Test getting services list."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "services": [
                            {
                                "id": "service:sshd",
                                "name": "sshd",
                                "online": True,
                                "uptime": {"timestamp": "2024-01-15T10:30:00Z"},
                                "version": "9.6",
                            },
                            {
                                "id": "service:docker",
                                "name": "docker",
                                "online": True,
                                "uptime": {"timestamp": "2024-01-15T10:30:00Z"},
                                "version": "24.0.7",
                            },
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_services()

                assert len(result) == 2
                assert result[0]["name"] == "sshd"
                assert result[0]["online"] is True

    async def test_typed_get_services(self) -> None:
        """Test getting services as Pydantic models."""
        from unraid_api.models import Service

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "services": [
                            {
                                "id": "service:sshd",
                                "name": "sshd",
                                "online": True,
                                "uptime": {"timestamp": "2024-01-15T10:30:00Z"},
                                "version": "9.6",
                            },
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_services()

                assert len(result) == 1
                assert isinstance(result[0], Service)
                assert result[0].name == "sshd"
                assert result[0].online is True


class TestGetFlashMethod:
    """Tests for get_flash and typed_get_flash methods."""

    async def test_get_flash(self) -> None:
        """Test getting flash drive information."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "flash": {
                            "id": "flash:1",
                            "product": "Ultra Fit",
                            "vendor": "SanDisk",
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_flash()

                assert result["vendor"] == "SanDisk"

    async def test_typed_get_flash(self) -> None:
        """Test getting flash drive as Pydantic model."""
        from unraid_api.models import Flash

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "flash": {
                            "id": "flash:1",
                            "product": "Ultra Fit",
                            "vendor": "SanDisk",
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_flash()

                assert isinstance(result, Flash)
                assert result.vendor == "SanDisk"


class TestGetOwnerMethod:
    """Tests for get_owner and typed_get_owner methods."""

    async def test_get_owner(self) -> None:
        """Test getting owner information."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "owner": {
                            "username": "admin",
                            "avatar": "https://example.com/avatar.png",
                            "url": "https://my.unraid.net",
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_owner()

                assert result["username"] == "admin"

    async def test_typed_get_owner(self) -> None:
        """Test getting owner as Pydantic model."""
        from unraid_api.models import Owner

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "owner": {
                            "username": "admin",
                            "avatar": None,
                            "url": None,
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_owner()

                assert isinstance(result, Owner)
                assert result.username == "admin"


class TestGetPluginsMethod:
    """Tests for get_plugins and typed_get_plugins methods."""

    async def test_get_plugins(self) -> None:
        """Test getting installed plugins."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "plugins": [
                            {
                                "name": "Dynamix System Stats",
                                "version": "2024.01.01",
                                "hasApiModule": True,
                                "hasCliModule": False,
                            }
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_plugins()

                assert len(result) == 1
                assert result[0]["name"] == "Dynamix System Stats"

    async def test_typed_get_plugins(self) -> None:
        """Test getting plugins as Pydantic models."""
        from unraid_api.models import Plugin

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "plugins": [
                            {
                                "name": "Test Plugin",
                                "version": "1.0",
                                "hasApiModule": True,
                                "hasCliModule": None,
                            }
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_plugins()

                assert len(result) == 1
                assert isinstance(result[0], Plugin)
                assert result[0].hasApiModule is True


class TestGetDockerNetworksMethod:
    """Tests for get_docker_networks and typed_get_docker_networks methods."""

    async def test_get_docker_networks(self) -> None:
        """Test getting Docker networks."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "docker": {
                            "networks": [
                                {
                                    "id": "network:bridge",
                                    "name": "bridge",
                                    "created": "2024-01-01T00:00:00Z",
                                    "scope": "local",
                                    "driver": "bridge",
                                    "enableIPv6": False,
                                    "internal": False,
                                    "attachable": False,
                                    "ingress": False,
                                    "configOnly": False,
                                }
                            ]
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_docker_networks()

                assert len(result) == 1
                assert result[0]["name"] == "bridge"

    async def test_typed_get_docker_networks(self) -> None:
        """Test getting Docker networks as Pydantic models."""
        from unraid_api.models import DockerNetwork

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "docker": {
                            "networks": [
                                {
                                    "id": "network:br0",
                                    "name": "br0",
                                    "created": None,
                                    "scope": "local",
                                    "driver": "macvlan",
                                    "enableIPv6": False,
                                    "internal": False,
                                    "attachable": False,
                                    "ingress": False,
                                    "configOnly": False,
                                }
                            ]
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_docker_networks()

                assert len(result) == 1
                assert isinstance(result[0], DockerNetwork)
                assert result[0].driver == "macvlan"


class TestGetLogFilesMethod:
    """Tests for get_log_files and typed_get_log_files methods."""

    async def test_get_log_files(self) -> None:
        """Test getting log files list."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "logFiles": [
                            {
                                "id": "log:syslog",
                                "name": "syslog",
                                "path": "/var/log/syslog",
                            },
                            {
                                "id": "log:docker",
                                "name": "docker",
                                "path": "/var/log/docker.log",
                            },
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_log_files()

                assert len(result) == 2
                assert result[0]["name"] == "syslog"

    async def test_typed_get_log_files(self) -> None:
        """Test getting log files as Pydantic models."""
        from unraid_api.models import LogFile

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "logFiles": [
                            {
                                "id": "log:syslog",
                                "name": "syslog",
                                "path": "/var/log/syslog",
                            }
                        ]
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_log_files()

                assert len(result) == 1
                assert isinstance(result[0], LogFile)
                assert result[0].path == "/var/log/syslog"

    async def test_get_log_file(self) -> None:
        """Test getting log file contents."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "logFile": {"log": "Jan 1 00:00:00 server test: Log entry\n"}
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_log_file("log:syslog")

                assert "log" in result
                assert "Log entry" in result["log"]

    async def test_get_log_file_with_lines(self) -> None:
        """Test getting log file contents with lines parameter."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "logFile": {
                            "path": "/var/log/syslog",
                            "content": "Line 1\nLine 2\n",
                            "totalLines": 100,
                            "startLine": 90,
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_log_file("log:syslog", lines=10)

                assert "content" in result
                assert result["totalLines"] == 100


class TestGetArrayDisksMethod:
    """Tests for get_array_disks method."""

    async def test_get_array_disks(self) -> None:
        """Test getting array disk info without waking disks."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "array": {
                            "boot": {
                                "id": "boot:0",
                                "name": "Flash",
                                "device": "sda",
                                "size": 16000000000,
                                "status": "DISK_OK",
                                "type": "Flash",
                                "temp": None,
                                "fsSize": 15000000000,
                                "fsUsed": 5000000000,
                                "fsFree": 10000000000,
                                "fsType": "vfat",
                            },
                            "disks": [
                                {
                                    "id": "disk:1",
                                    "idx": 1,
                                    "name": "Disk 1",
                                    "device": "sdb",
                                    "size": 4000000000000,
                                    "status": "DISK_OK",
                                    "type": "Data",
                                    "temp": 35,
                                    "fsSize": 3900000000000,
                                    "fsUsed": 2000000000000,
                                    "fsFree": 1900000000000,
                                    "fsType": "xfs",
                                    "isSpinning": True,
                                }
                            ],
                            "parities": [
                                {
                                    "id": "parity:0",
                                    "idx": 0,
                                    "name": "Parity",
                                    "device": "sdc",
                                    "size": 4000000000000,
                                    "status": "DISK_OK",
                                    "type": "Parity",
                                    "temp": 33,
                                    "isSpinning": True,
                                }
                            ],
                            "caches": [
                                {
                                    "id": "cache:0",
                                    "idx": 0,
                                    "name": "Cache",
                                    "device": "nvme0n1",
                                    "size": 500000000000,
                                    "status": "DISK_OK",
                                    "type": "Cache",
                                    "temp": 40,
                                    "fsSize": 480000000000,
                                    "fsUsed": 100000000000,
                                    "fsFree": 380000000000,
                                    "fsType": "btrfs",
                                    "isSpinning": False,
                                }
                            ],
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_array_disks()

                assert result["boot"]["id"] == "boot:0"
                assert len(result["disks"]) == 1
                assert result["disks"][0]["isSpinning"] is True
                assert len(result["parities"]) == 1
                assert len(result["caches"]) == 1


class TestGetCloudMethod:
    """Tests for get_cloud and typed_get_cloud methods."""

    async def test_get_cloud(self) -> None:
        """Test getting cloud settings."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "cloud": {
                            "error": None,
                            "apiKey": {"valid": True, "error": None},
                            "relay": {"status": "connected", "timeout": "5000"},
                            "minigraphql": {"status": "CONNECTED", "timeout": 30},
                            "cloud": {"status": "ok", "ip": "192.168.1.100"},
                            "allowedOrigins": ["http://localhost"],
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_cloud()

                assert result["cloud"]["status"] == "ok"

    async def test_typed_get_cloud(self) -> None:
        """Test getting cloud settings as Pydantic model."""
        from unraid_api.models import Cloud

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "cloud": {
                            "error": None,
                            "apiKey": {"valid": True, "error": None},
                            "relay": None,
                            "minigraphql": {"status": "CONNECTED"},
                            "cloud": {"status": "ok", "ip": None},
                            "allowedOrigins": [],
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_cloud()

                assert isinstance(result, Cloud)
                assert result.cloud is not None
                assert result.cloud.status == "ok"


class TestGetConnectMethod:
    """Tests for get_connect and typed_get_connect methods."""

    async def test_get_connect(self) -> None:
        """Test getting Unraid Connect information."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "connect": {
                            "id": "connect:1",
                            "dynamicRemoteAccess": {
                                "enabledType": "UPNP",
                                "runningType": "UPNP",
                                "error": None,
                            },
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_connect()

                assert result["dynamicRemoteAccess"]["enabledType"] == "UPNP"

    async def test_typed_get_connect(self) -> None:
        """Test getting Connect as Pydantic model."""
        from unraid_api.models import Connect

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "connect": {
                            "id": "connect:1",
                            "dynamicRemoteAccess": {
                                "enabledType": "DISABLED",
                                "runningType": "DISABLED",
                                "error": None,
                            },
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_connect()

                assert isinstance(result, Connect)
                assert result.dynamicRemoteAccess is not None
                assert result.dynamicRemoteAccess.enabledType == "DISABLED"


class TestGetRemoteAccessMethod:
    """Tests for get_remote_access and typed_get_remote_access methods."""

    async def test_get_remote_access(self) -> None:
        """Test getting remote access configuration."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "remoteAccess": {
                            "accessType": "ALWAYS",
                            "forwardType": "UPNP",
                            "port": 443,
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.get_remote_access()

                assert result["accessType"] == "ALWAYS"
                assert result["port"] == 443

    async def test_typed_get_remote_access(self) -> None:
        """Test getting remote access as Pydantic model."""
        from unraid_api.models import RemoteAccess

        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "remoteAccess": {
                            "accessType": "DISABLED",
                            "forwardType": None,
                            "port": None,
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.typed_get_remote_access()

                assert isinstance(result, RemoteAccess)
                assert result.accessType == "DISABLED"


class TestNotificationMutations:
    """Tests for notification mutation methods."""

    async def test_archive_notification(self) -> None:
        """Test archiving a notification."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "notifications": {
                            "archive": {"id": "notification:123", "title": "Test"}
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.archive_notification("notification:123")

                assert "notifications" in result
                assert result["notifications"]["archive"]["id"] == "notification:123"

    async def test_unarchive_notification(self) -> None:
        """Test unarchiving a notification."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "notifications": {
                            "unread": {"id": "notification:123", "title": "Test"}
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.unarchive_notification("notification:123")

                assert "notifications" in result

    async def test_delete_notification(self) -> None:
        """Test deleting a notification."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"notifications": {"delete": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.delete_notification("notification:123")

                assert result["notifications"]["delete"] is True

    async def test_archive_all_notifications(self) -> None:
        """Test archiving all notifications."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"notifications": {"archiveAll": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.archive_all_notifications()

                assert result["notifications"]["archiveAll"] is True

    async def test_delete_all_notifications(self) -> None:
        """Test deleting all notifications."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"notifications": {"deleteAll": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.delete_all_notifications()

                assert result["notifications"]["deleteAll"] is True


class TestResetVmMethod:
    """Tests for reset_vm method."""

    async def test_reset_vm(self) -> None:
        """Test resetting a virtual machine."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={"data": {"vm": {"reset": True}}},
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.reset_vm("vm:test-vm")

                assert result["vm"]["reset"] is True


class TestArrayDiskManagementMethods:
    """Tests for array disk management methods."""

    async def test_add_array_disk(self) -> None:
        """Test adding a disk to the array."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "array": {
                            "addDisk": {
                                "id": "disk:sdb",
                                "name": "disk1",
                                "status": "active",
                            }
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.add_array_disk("disk:sdb")

                assert result["array"]["addDisk"]["id"] == "disk:sdb"

    async def test_remove_array_disk(self) -> None:
        """Test removing a disk from the array."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "array": {
                            "removeDisk": {
                                "id": "disk:sdb",
                                "name": "disk1",
                                "status": "unassigned",
                            }
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.remove_array_disk("disk:sdb")

                assert "removeDisk" in result["array"]

    async def test_clear_disk_stats(self) -> None:
        """Test clearing disk statistics."""
        with aioresponses() as m:
            m.get("http://192.168.1.100/graphql", status=400)
            m.post(
                "http://192.168.1.100/graphql",
                payload={
                    "data": {
                        "array": {
                            "clearStatistics": {"id": "disk:sdb", "name": "disk1"}
                        }
                    }
                },
            )

            async with UnraidClient(
                "192.168.1.100", "test-key", verify_ssl=False
            ) as client:
                result = await client.clear_disk_stats("disk:sdb")

                assert "clearStatistics" in result["array"]
