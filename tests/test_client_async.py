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
    UnraidTimeoutError,
)


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
            m.get("http://192.168.1.100/graphql", status=400)

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
