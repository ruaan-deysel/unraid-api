"""Async GraphQL client for Unraid server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import aiohttp

from unraid_api.exceptions import (
    UnraidAPIError,
    UnraidAuthenticationError,
    UnraidConnectionError,
    UnraidSSLError,
    UnraidTimeoutError,
)

if TYPE_CHECKING:
    import ssl
    from types import TracebackType

    from unraid_api.models import (
        Cloud,
        Connect,
        DockerContainer,
        DockerNetwork,
        Flash,
        LogFile,
        NotificationOverview,
        Owner,
        Plugin,
        Registration,
        RemoteAccess,
        ServerInfo,
        Service,
        Share,
        SystemMetrics,
        UnraidArray,
        UPSDevice,
        Vars,
        VmDomain,
    )


_LOGGER = logging.getLogger(__name__)

# HTTP status codes
HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
DEFAULT_HTTP_PORT = 80
DEFAULT_HTTPS_PORT = 443


class UnraidClient:
    """Async client for interacting with Unraid GraphQL API.

    This client handles:
    - SSL/TLS mode detection (No, Yes, Strict)
    - Automatic redirect discovery for myunraid.net
    - Session management with proper cleanup
    - GraphQL query and mutation execution

    Example:
        async with UnraidClient("192.168.1.100", "your-api-key") as client:
            if await client.test_connection():
                info = await client.get_system_info()

    """

    def __init__(
        self,
        host: str,
        api_key: str,
        *,
        http_port: int = DEFAULT_HTTP_PORT,
        https_port: int = DEFAULT_HTTPS_PORT,
        verify_ssl: bool = True,
        timeout: int = 30,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the API client.

        Args:
            host: Server hostname or IP (with or without http:// or https://).
            api_key: Unraid API key with ADMIN role.
            http_port: HTTP port for redirect discovery (default 80).
            https_port: HTTPS port (default 443).
            verify_ssl: Whether to verify SSL certificates (default True).
            timeout: Request timeout in seconds (default 30s).
            session: Optional aiohttp session (for HA websession injection).

        """
        self.host = host.strip()
        self.http_port = http_port
        self.https_port = https_port
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._api_key = api_key
        self._session: aiohttp.ClientSession | None = session
        self._owns_session: bool = session is None
        self._resolved_url: str | None = None

    @property
    def session(self) -> aiohttp.ClientSession | None:
        """Get the aiohttp session."""
        return self._session

    async def __aenter__(self) -> UnraidClient:
        """Async context manager entry."""
        await self._create_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def _create_session(self) -> None:
        """Create aiohttp session with proper SSL configuration."""
        if self._session is not None:
            return

        ssl_context: ssl.SSLContext | bool | None = None
        if not self.verify_ssl:
            ssl_context = False
            _LOGGER.warning(
                "SSL verification disabled for %s. "
                "Connection is encrypted but server identity is not verified.",
                self.host,
            )
        else:
            ssl_context = True

        connector = aiohttp.TCPConnector(ssl=ssl_context, force_close=False)
        timeout_config = aiohttp.ClientTimeout(total=self.timeout)

        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout_config,
            headers={"x-api-key": self._api_key},
        )
        self._owns_session = True

    async def close(self) -> None:
        """Close the aiohttp session if we created it."""
        if self._session is not None and self._owns_session:
            await self._session.close()
            self._session = None

    def _get_clean_host(self) -> str:
        """Get host without protocol prefix."""
        clean_host = self.host
        if "://" in clean_host:
            clean_host = clean_host.split("://", 1)[1]
        return clean_host.rstrip("/")

    async def _discover_redirect_url(self) -> tuple[str | None, bool]:
        """Discover the correct URL and SSL mode for the Unraid server.

        Unraid servers have three SSL/TLS modes:
        - No: HTTP only, no redirect
        - Yes: HTTP redirects to HTTPS (self-signed certificate)
        - Strict: HTTP redirects to myunraid.net (valid certificate)

        Returns:
            Tuple of (redirect_url, use_ssl):
            - (myunraid_url, True) for Strict mode
            - (https_url, True) for Yes mode
            - (None, False) for No mode (HTTP works directly)
            - (None, True) if HTTP check fails (fallback to HTTPS)

        """
        if self._session is None:
            await self._create_session()

        if self._session is None:
            raise UnraidConnectionError("Failed to create HTTP session")

        clean_host = self._get_clean_host()

        # Short-circuit: if http_port == https_port, assume this port is configured
        # to serve HTTPS and skip the plain HTTP probe to avoid a likely 400 from nginx.
        if self.http_port == self.https_port:
            _LOGGER.debug(
                "http_port == https_port (%d), assuming HTTPS for %s",
                self.http_port,
                clean_host,
            )
            return (None, True)

        http_port_suffix = (
            "" if self.http_port == DEFAULT_HTTP_PORT else f":{self.http_port}"
        )

        http_url = f"http://{clean_host}{http_port_suffix}/graphql"
        _LOGGER.debug("Checking for redirect at %s", http_url)

        headers = {"x-api-key": self._api_key}

        try:
            async with self._session.get(
                http_url, headers=headers, allow_redirects=False
            ) as response:
                _LOGGER.debug("HTTP response status: %d", response.status)

                if response.status in (301, 302, 307, 308):
                    redirect_url = response.headers.get("Location")
                    _LOGGER.debug("Redirect location: %s", redirect_url)
                    if redirect_url:
                        parsed = urlparse(redirect_url)
                        hostname = parsed.hostname

                        # Check for myunraid.net redirect (Strict mode)
                        if hostname and (
                            hostname == "myunraid.net"
                            or hostname.endswith(".myunraid.net")
                        ):
                            _LOGGER.info(
                                "Discovered myunraid.net redirect (Strict mode): %s",
                                redirect_url,
                            )
                            return (redirect_url, True)

                        # Check for HTTPS redirect (Yes mode)
                        if parsed.scheme == "https":
                            port = parsed.port
                            if port == DEFAULT_HTTPS_PORT:
                                normalized = f"https://{hostname}{parsed.path}"
                            else:
                                normalized = redirect_url
                            _LOGGER.info(
                                "Discovered HTTPS redirect (Yes mode): %s",
                                normalized,
                            )
                            return (normalized, True)

                # Detect nginx returning 400 when plain HTTP hits an HTTPS port
                if response.status == 400:
                    body = await response.text()
                    if "the plain http request was sent to https port" in body.lower():
                        _LOGGER.info(
                            "HTTP probe got 400 'plain HTTP to HTTPS port' from %s, "
                            "server requires HTTPS",
                            clean_host,
                        )
                        return (None, True)

                # HTTP endpoint is accessible (SSL/TLS mode is "No")
                _LOGGER.info(
                    "HTTP endpoint accessible (status %d), SSL/TLS mode is 'No' for %s",
                    response.status,
                    clean_host,
                )
                return (None, False)

        except aiohttp.ClientError as err:
            _LOGGER.debug("HTTP check failed, will try HTTPS: %s", err)

        return (None, True)

    async def _make_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Make a GraphQL request to the Unraid server.

        Args:
            payload: GraphQL query/mutation payload.

        Returns:
            Response data dictionary.

        Raises:
            UnraidConnectionError: On network errors.
            UnraidAuthenticationError: On authentication failures.
            UnraidTimeoutError: On request timeout.

        """
        if self._session is None:
            await self._create_session()

        if self._session is None:
            raise UnraidConnectionError("Failed to create HTTP session")

        if self._resolved_url is None:
            redirect_url, use_ssl = await self._discover_redirect_url()
            if redirect_url:
                self._resolved_url = redirect_url
            else:
                clean_host = self._get_clean_host()
                if use_ssl:
                    protocol = "https"
                    port_suffix = (
                        f":{self.https_port}"
                        if self.https_port != DEFAULT_HTTPS_PORT
                        else ""
                    )
                else:
                    protocol = "http"
                    port_suffix = (
                        f":{self.http_port}"
                        if self.http_port != DEFAULT_HTTP_PORT
                        else ""
                    )
                self._resolved_url = f"{protocol}://{clean_host}{port_suffix}/graphql"
            _LOGGER.debug("Using URL: %s", self._resolved_url)

        url = self._resolved_url
        headers = {"x-api-key": self._api_key}

        try:
            async with self._session.post(
                url, json=payload, headers=headers, allow_redirects=False
            ) as response:
                # Follow redirects if needed
                if response.status in (301, 302, 307, 308):
                    redirect_url = response.headers.get("Location")
                    if redirect_url:
                        self._resolved_url = redirect_url
                        async with self._session.post(
                            redirect_url,
                            json=payload,
                            headers=headers,
                            allow_redirects=False,
                        ) as redirect_response:
                            redirect_response.raise_for_status()
                            result: dict[str, Any] = await redirect_response.json()
                            return result
                    raise UnraidConnectionError(
                        f"Redirect {response.status} without Location header"
                    )

                if response.status in (HTTP_UNAUTHORIZED, HTTP_FORBIDDEN):
                    raise UnraidAuthenticationError(
                        "Invalid API key or insufficient permissions"
                    )

                response.raise_for_status()
                json_result: dict[str, Any] = await response.json()
                return json_result

        except TimeoutError as err:
            raise UnraidTimeoutError(f"Request timed out: {err}") from err
        except aiohttp.ClientSSLError as err:
            raise UnraidSSLError(f"SSL certificate verification failed: {err}") from err
        except aiohttp.ClientError as err:
            raise UnraidConnectionError(f"Connection failed: {err}") from err

    async def query(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a GraphQL query.

        Args:
            query: GraphQL query string.
            variables: Optional query variables.

        Returns:
            Query response data (the 'data' field from GraphQL response).

        Raises:
            UnraidAPIError: On GraphQL errors with no data.
            UnraidConnectionError: On network errors.
            UnraidAuthenticationError: On authentication failures.

        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        response = await self._make_request(payload)
        data = response.get("data", {})

        if "errors" in response:
            errors = response["errors"]
            error_messages = []
            for err in errors:
                if isinstance(err, dict):
                    msg = err.get("message", str(err))
                    path = err.get("path")
                    if path:
                        msg = f"{msg} (path: {path})"
                    error_messages.append(msg)
                else:
                    error_messages.append(str(err))

            _LOGGER.debug("Full GraphQL error response: %s", errors)

            if data:
                # Partial failure - log and return data
                _LOGGER.debug(
                    "Some optional features unavailable: %s",
                    "; ".join(error_messages),
                )
            else:
                # Complete failure - raise exception
                _LOGGER.debug(
                    "GraphQL query returned no data with %d error(s): %s",
                    len(errors),
                    "; ".join(error_messages),
                )
                raise UnraidAPIError(
                    "GraphQL query failed",
                    errors=errors,
                )

        return dict(data)

    async def mutate(
        self, mutation: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a GraphQL mutation.

        Args:
            mutation: GraphQL mutation string.
            variables: Optional mutation variables.

        Returns:
            Mutation response data.

        Raises:
            UnraidAPIError: On GraphQL errors.
            UnraidConnectionError: On network errors.

        """
        return await self.query(mutation, variables)

    # =========================================================================
    # Connection & Info Methods
    # =========================================================================

    async def test_connection(self) -> bool:
        """Test connection to Unraid server.

        Returns:
            True if connection successful.

        Raises:
            UnraidConnectionError: On connection failure.

        """
        result = await self.query("query { online }")
        return bool(result.get("online", False))

    async def get_version(self) -> dict[str, str]:
        """Get Unraid server version information.

        Returns:
            Dictionary with 'unraid' and 'api' version strings.

        """
        query_str = """
            query {
                info {
                    versions {
                        core {
                            unraid
                            api
                        }
                    }
                }
            }
        """
        result = await self.query(query_str)
        versions = result.get("info", {}).get("versions", {}).get("core", {})
        return {
            "unraid": versions.get("unraid", "unknown"),
            "api": versions.get("api", "unknown"),
        }

    async def get_server_info(self) -> ServerInfo:
        """Get server information for device registration.

        Returns comprehensive server identification data useful for
        Home Assistant device registration and identification.

        Returns:
            ServerInfo model with all server identification data.

        """
        from unraid_api.models import ServerInfo

        query_str = """
            query {
                info {
                    system { uuid manufacturer model serial }
                    baseboard { manufacturer model serial }
                    os { hostname distro release kernel arch }
                    cpu { manufacturer brand cores threads }
                    versions { core { unraid api } }
                }
                server { lanip localurl remoteurl }
                registration { type state }
            }
        """
        result = await self.query(query_str)
        return ServerInfo.from_response(result)

    async def get_system_metrics(self) -> SystemMetrics:
        """Get system metrics for monitoring.

        Returns CPU, memory, swap, and uptime metrics for Home Assistant
        sensor entities. This is called every 30 seconds by the HA integration.

        Returns:
            SystemMetrics model with all metrics data.

        """
        from unraid_api.models import SystemMetrics

        query_str = """
            query {
                metrics {
                    cpu { percentTotal }
                    memory {
                        total used free available percentTotal
                        swapTotal swapUsed percentSwapTotal
                    }
                }
                info {
                    os { uptime }
                    cpu { packages { temp totalPower } }
                }
            }
        """
        result = await self.query(query_str)
        return SystemMetrics.from_response(result)

    async def typed_get_containers(self) -> list[DockerContainer]:
        """Get all Docker containers as Pydantic models.

        Returns:
            List of DockerContainer models.

        """
        from unraid_api.models import DockerContainer

        query_str = """
            query {
                docker {
                    containers {
                        id
                        names
                        image
                        state
                        status
                        autoStart
                        ports { ip privatePort publicPort type }
                    }
                }
            }
        """
        result = await self.query(query_str)
        containers = result.get("docker", {}).get("containers", []) or []
        return [DockerContainer.from_api_response(c) for c in containers]

    async def typed_get_vms(self) -> list[VmDomain]:
        """Get all virtual machines as Pydantic models.

        Returns:
            List of VmDomain models.

        """
        from unraid_api.models import VmDomain

        query_str = """
            query {
                vms {
                    domains {
                        id
                        name
                        state
                    }
                }
            }
        """
        result = await self.query(query_str)
        domains = result.get("vms", {}).get("domains", []) or []
        return [VmDomain(**vm) for vm in domains]

    async def typed_get_ups_devices(self) -> list[UPSDevice]:
        """Get UPS devices as Pydantic models.

        Returns:
            List of UPSDevice models.

        """
        from unraid_api.models import UPSDevice

        query_str = """
            query {
                upsDevices {
                    id
                    name
                    model
                    status
                    battery { chargeLevel estimatedRuntime health }
                    power { inputVoltage outputVoltage loadPercentage }
                }
            }
        """
        result = await self.query(query_str)
        devices = result.get("upsDevices", []) or []
        return [UPSDevice(**d) for d in devices]

    async def typed_get_array(self) -> UnraidArray:
        """Get array status as Pydantic model.

        This is a high-priority method for Home Assistant integration,
        called every 30 seconds. Does NOT wake sleeping disks.

        Returns:
            UnraidArray model with array state, capacity, and disk info.

        """
        from unraid_api.models import ArrayDisk, UnraidArray

        query_str = """
            query {
                array {
                    state
                    capacity {
                        kilobytes { free used total }
                    }
                    parityCheckStatus {
                        status
                        progress
                        running
                        paused
                        errors
                        speed
                    }
                    boot {
                        id name device size temp type
                        fsSize fsUsed fsFree fsType
                    }
                    parities {
                        id idx name device size status type temp
                        isSpinning
                    }
                    disks {
                        id idx name device size status type temp
                        fsSize fsFree fsUsed fsType
                        isSpinning
                    }
                    caches {
                        id idx name device size status type temp
                        fsSize fsFree fsUsed fsType
                        isSpinning
                    }
                }
            }
        """
        result = await self.query(query_str)
        array_data = result.get("array", {}) or {}

        # Parse nested models
        boot_data = array_data.get("boot")
        boot = ArrayDisk(**boot_data) if boot_data else None

        return UnraidArray(
            state=array_data.get("state"),
            capacity=array_data.get("capacity", {}),
            parityCheckStatus=array_data.get("parityCheckStatus", {}),
            boot=boot,
            parities=[ArrayDisk(**d) for d in (array_data.get("parities") or [])],
            disks=[ArrayDisk(**d) for d in (array_data.get("disks") or [])],
            caches=[ArrayDisk(**d) for d in (array_data.get("caches") or [])],
        )

    async def typed_get_shares(self) -> list[Share]:
        """Get all shares as Pydantic models.

        Returns:
            List of Share models.

        """
        from unraid_api.models import Share

        query_str = """
            query {
                shares {
                    id
                    name
                    free
                    used
                    size
                }
            }
        """
        result = await self.query(query_str)
        shares = result.get("shares", []) or []
        return [Share(**s) for s in shares]

    async def get_notification_overview(self) -> NotificationOverview:
        """Get notification overview as Pydantic model.

        Returns notification counts by type (info, warning, alert)
        for both unread and archived notifications.

        Returns:
            NotificationOverview model with notification counts.

        """
        from unraid_api.models import NotificationOverview

        query_str = """
            query {
                notifications {
                    overview {
                        unread { info warning alert total }
                        archive { info warning alert total }
                    }
                }
            }
        """
        result = await self.query(query_str)
        overview_data = result.get("notifications", {}).get("overview", {}) or {}
        return NotificationOverview(**overview_data)

    # =========================================================================
    # Docker Container Methods
    # =========================================================================

    async def start_container(self, container_id: str) -> dict[str, Any]:
        """Start a Docker container.

        Args:
            container_id: Container ID to start.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation StartContainer($id: PrefixedID!) {
                docker {
                    start(id: $id) {
                        id
                        state
                        status
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": container_id})

    async def stop_container(self, container_id: str) -> dict[str, Any]:
        """Stop a Docker container.

        Args:
            container_id: Container ID to stop.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation StopContainer($id: PrefixedID!) {
                docker {
                    stop(id: $id) {
                        id
                        state
                        status
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": container_id})

    # =========================================================================
    # Virtual Machine Methods
    # =========================================================================

    async def start_vm(self, vm_id: str) -> dict[str, Any]:
        """Start a virtual machine.

        Args:
            vm_id: VM ID to start.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation StartVM($id: PrefixedID!) {
                vm {
                    start(id: $id)
                }
            }
        """
        return await self.mutate(mutation, {"id": vm_id})

    async def stop_vm(self, vm_id: str) -> dict[str, Any]:
        """Stop a virtual machine.

        Args:
            vm_id: VM ID to stop.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation StopVM($id: PrefixedID!) {
                vm {
                    stop(id: $id)
                }
            }
        """
        return await self.mutate(mutation, {"id": vm_id})

    # =========================================================================
    # Array Control Methods
    # =========================================================================

    async def start_array(self) -> dict[str, Any]:
        """Start the Unraid array.

        WARNING: This is a potentially destructive operation.

        Returns:
            Mutation response data with array state.

        """
        mutation = """
            mutation StartArray {
                array {
                    setState(input: { desiredState: START }) {
                        id
                        state
                    }
                }
            }
        """
        return await self.mutate(mutation)

    async def stop_array(self) -> dict[str, Any]:
        """Stop the Unraid array.

        WARNING: This is a destructive operation. All containers and VMs
        using array storage will be affected.

        Returns:
            Mutation response data with array state.

        """
        mutation = """
            mutation StopArray {
                array {
                    setState(input: { desiredState: STOP }) {
                        id
                        state
                    }
                }
            }
        """
        return await self.mutate(mutation)

    # =========================================================================
    # Parity Check Control Methods
    # =========================================================================

    async def start_parity_check(self, *, correct: bool = False) -> dict[str, Any]:
        """Start a parity check.

        Args:
            correct: If True, write corrections to parity. If False, read-only.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation StartParityCheck($correct: Boolean!) {
                parityCheck {
                    start(correct: $correct)
                }
            }
        """
        return await self.mutate(mutation, {"correct": correct})

    async def pause_parity_check(self) -> dict[str, Any]:
        """Pause a running parity check.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation PauseParityCheck {
                parityCheck {
                    pause
                }
            }
        """
        return await self.mutate(mutation)

    async def resume_parity_check(self) -> dict[str, Any]:
        """Resume a paused parity check.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation ResumeParityCheck {
                parityCheck {
                    resume
                }
            }
        """
        return await self.mutate(mutation)

    async def cancel_parity_check(self) -> dict[str, Any]:
        """Cancel a running parity check.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation CancelParityCheck {
                parityCheck {
                    cancel
                }
            }
        """
        return await self.mutate(mutation)

    # =========================================================================
    # Disk Spin Control Methods
    # =========================================================================

    async def spin_up_disk(self, disk_id: str) -> dict[str, Any]:
        """Spin up (mount) a disk in the array.

        Args:
            disk_id: Disk ID to spin up (e.g., "disk:1").

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation SpinUpDisk($id: PrefixedID!) {
                array {
                    mountArrayDisk(id: $id) {
                        id
                        isSpinning
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": disk_id})

    async def spin_down_disk(self, disk_id: str) -> dict[str, Any]:
        """Spin down (unmount) a disk in the array.

        Args:
            disk_id: Disk ID to spin down (e.g., "disk:1").

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation SpinDownDisk($id: PrefixedID!) {
                array {
                    unmountArrayDisk(id: $id) {
                        id
                        isSpinning
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": disk_id})

    # =========================================================================
    # Additional Docker Container Methods
    # =========================================================================

    async def pause_container(self, container_id: str) -> dict[str, Any]:
        """Pause (suspend) a Docker container.

        Args:
            container_id: Container ID to pause.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation PauseContainer($id: PrefixedID!) {
                docker {
                    pause(id: $id) {
                        id
                        state
                        status
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": container_id})

    async def unpause_container(self, container_id: str) -> dict[str, Any]:
        """Unpause (resume) a Docker container.

        Args:
            container_id: Container ID to unpause.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation UnpauseContainer($id: PrefixedID!) {
                docker {
                    unpause(id: $id) {
                        id
                        state
                        status
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": container_id})

    async def update_container(self, container_id: str) -> dict[str, Any]:
        """Update a container to the latest image.

        Args:
            container_id: Container ID to update.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation UpdateContainer($id: PrefixedID!) {
                docker {
                    updateContainer(id: $id) {
                        id
                        names
                        image
                        state
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": container_id})

    async def get_containers(self) -> list[dict[str, Any]]:
        """Get all Docker containers.

        Returns:
            List of container data dictionaries.

        """
        # Using core fields guaranteed across API versions
        query_str = """
            query {
                docker {
                    containers {
                        id
                        names
                        image
                        imageId
                        state
                        status
                        autoStart
                        command
                        created
                        ports { ip privatePort publicPort type }
                    }
                }
            }
        """
        result = await self.query(query_str)
        return list(result.get("docker", {}).get("containers", []))

    # =========================================================================
    # Additional VM Methods
    # =========================================================================

    async def pause_vm(self, vm_id: str) -> dict[str, Any]:
        """Pause a virtual machine.

        Args:
            vm_id: VM ID to pause.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation PauseVM($id: PrefixedID!) {
                vm {
                    pause(id: $id)
                }
            }
        """
        return await self.mutate(mutation, {"id": vm_id})

    async def resume_vm(self, vm_id: str) -> dict[str, Any]:
        """Resume a paused virtual machine.

        Args:
            vm_id: VM ID to resume.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation ResumeVM($id: PrefixedID!) {
                vm {
                    resume(id: $id)
                }
            }
        """
        return await self.mutate(mutation, {"id": vm_id})

    async def force_stop_vm(self, vm_id: str) -> dict[str, Any]:
        """Force stop a virtual machine.

        Args:
            vm_id: VM ID to force stop.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation ForceStopVM($id: PrefixedID!) {
                vm {
                    forceStop(id: $id)
                }
            }
        """
        return await self.mutate(mutation, {"id": vm_id})

    async def reboot_vm(self, vm_id: str) -> dict[str, Any]:
        """Reboot a virtual machine.

        Args:
            vm_id: VM ID to reboot.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation RebootVM($id: PrefixedID!) {
                vm {
                    reboot(id: $id)
                }
            }
        """
        return await self.mutate(mutation, {"id": vm_id})

    async def get_vms(self) -> list[dict[str, Any]]:
        """Get all virtual machines.

        Returns:
            List of VM data dictionaries.

        """
        query_str = """
            query {
                vms {
                    domains {
                        id
                        name
                        state
                    }
                }
            }
        """
        result = await self.query(query_str)
        return list(result.get("vms", {}).get("domains", []) or [])

    # =========================================================================
    # System Metrics Methods
    # =========================================================================

    async def get_metrics(self) -> dict[str, Any]:
        """Get system CPU and memory metrics.

        Returns:
            Metrics data with cpu and memory utilization.

        """
        query_str = """
            query {
                metrics {
                    cpu {
                        percentTotal
                        cpus {
                            percentTotal
                            percentUser
                            percentSystem
                            percentIdle
                        }
                    }
                    memory {
                        total
                        used
                        free
                        available
                        percentTotal
                        swapTotal
                        swapUsed
                        swapFree
                        percentSwapTotal
                    }
                }
            }
        """
        result = await self.query(query_str)
        return dict(result.get("metrics", {}))

    async def get_system_info(self) -> dict[str, Any]:
        """Get comprehensive system information.

        Returns:
            System info including OS, CPU, memory, versions.

        """
        query_str = """
            query {
                info {
                    time
                    os {
                        hostname
                        uptime
                        kernel
                        platform
                        distro
                        arch
                    }
                    cpu {
                        manufacturer
                        brand
                        cores
                        threads
                        speed
                    }
                    memory {
                        layout {
                            size
                            bank
                            type
                            clockSpeed
                            manufacturer
                        }
                    }
                    versions {
                        core { unraid api kernel }
                        packages { docker openssl node }
                    }
                    baseboard {
                        manufacturer
                        model
                        memMax
                        memSlots
                    }
                }
            }
        """
        result = await self.query(query_str)
        return dict(result.get("info", {}))

    # =========================================================================
    # Array Information Methods
    # =========================================================================

    async def get_array_status(self) -> dict[str, Any]:
        """Get comprehensive array status.

        This method does NOT wake sleeping disks - it's safe for periodic polling.
        Temperature will be null/0 for disks in standby mode.
        Use the isSpinning field to check if a disk is active.

        Returns:
            Array data including state, capacity, disks, and parity status.

        """
        query_str = """
            query {
                array {
                    state
                    capacity {
                        kilobytes { free used total }
                        disks { free used total }
                    }
                    parityCheckStatus {
                        status
                        progress
                        running
                        paused
                        errors
                        speed
                    }
                    boot {
                        id name device size temp type
                        fsSize fsUsed fsFree fsType
                    }
                    parities {
                        id idx name device size status type temp
                        isSpinning
                    }
                    disks {
                        id idx name device size status type temp
                        fsSize fsFree fsUsed fsType
                        isSpinning
                    }
                    caches {
                        id idx name device size status type temp
                        fsSize fsFree fsUsed fsType
                        isSpinning
                    }
                }
            }
        """
        result = await self.query(query_str)
        return dict(result.get("array", {}))

    # =========================================================================
    # Share Methods
    # =========================================================================

    async def get_shares(self) -> list[dict[str, Any]]:
        """Get all user shares.

        Returns:
            List of share data dictionaries.

        """
        query_str = """
            query {
                shares {
                    id
                    name
                    free
                    used
                    size
                    cache
                    comment
                    include
                    exclude
                }
            }
        """
        result = await self.query(query_str)
        return list(result.get("shares", []))

    # =========================================================================
    # UPS Methods
    # =========================================================================

    async def get_ups_status(self) -> list[dict[str, Any]]:
        """Get UPS device status.

        Returns:
            List of UPS device data.

        """
        query_str = """
            query {
                upsDevices {
                    id
                    name
                    model
                    status
                    battery {
                        chargeLevel
                        estimatedRuntime
                        health
                    }
                    power {
                        inputVoltage
                        outputVoltage
                        loadPercentage
                    }
                }
            }
        """
        result = await self.query(query_str)
        return list(result.get("upsDevices", []))

    # =========================================================================
    # Notification Methods
    # =========================================================================

    async def get_notifications(
        self,
        notification_type: str = "UNREAD",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get notifications.

        Args:
            notification_type: Type of notifications ("UNREAD" or "ARCHIVE").
            limit: Maximum number of notifications to return.
            offset: Offset for pagination.

        Returns:
            Notifications data including overview and list.

        """
        query_str = """
            query GetNotifications(
                $type: NotificationType!
                $limit: Int!
                $offset: Int!
            ) {
                notifications {
                    overview {
                        unread { info warning alert total }
                        archive { info warning alert total }
                    }
                    list(filter: { type: $type, limit: $limit, offset: $offset }) {
                        id
                        title
                        subject
                        description
                        importance
                        timestamp
                    }
                }
            }
        """
        result = await self.query(
            query_str,
            {"type": notification_type, "limit": limit, "offset": offset},
        )
        return dict(result.get("notifications", {}))

    # =========================================================================
    # Additional Docker Methods
    # =========================================================================

    async def remove_container(
        self, container_id: str, *, with_image: bool = False
    ) -> dict[str, Any]:
        """Remove a Docker container.

        Args:
            container_id: Container ID to remove.
            with_image: Also remove the container's image.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation RemoveContainer($id: PrefixedID!, $withImage: Boolean!) {
                docker {
                    removeContainer(id: $id, withImage: $withImage)
                }
            }
        """
        return await self.mutate(
            mutation, {"id": container_id, "withImage": with_image}
        )

    # =========================================================================
    # Physical Disk Methods
    # =========================================================================

    async def get_physical_disks(
        self, include_smart: bool = False
    ) -> list[dict[str, Any]]:
        """Get all physical disks.

        WARNING: This query WILL WAKE UP sleeping/standby disks!
        For disk information without waking disks, use get_array_disks() instead.

        Args:
            include_smart: If True, include SMART status (may cause disk wake).

        Returns:
            List of physical disk data dictionaries.

        Note:
            The Unraid API's physical disks endpoint requires disk access which
            spins up any sleeping disks. If you need disk status without waking
            disks, use get_array_disks() which uses the array endpoint that
            provides disk info (including temperature for spinning disks and
            isSpinning status) without forcing disks to wake up.

        """
        # Build query with optional SMART fields
        smart_fields = "smartStatus" if include_smart else ""
        query_str = f"""
            query {{
                disks {{
                    id
                    device
                    name
                    vendor
                    size
                    type
                    interfaceType
                    temperature
                    isSpinning
                    {smart_fields}
                }}
            }}
        """
        result = await self.query(query_str)
        return list(result.get("disks", []))

    # Alias for backwards compatibility - deprecated
    async def get_disks(self) -> list[dict[str, Any]]:
        """Get all physical disks.

        DEPRECATED: Use get_physical_disks() or get_array_disks() instead.

        WARNING: This query WILL WAKE UP sleeping/standby disks!
        Use get_array_disks() for disk info without waking disks.

        Returns:
            List of physical disk data dictionaries.

        """
        return await self.get_physical_disks(include_smart=False)

    async def get_array_disks(self) -> dict[str, Any]:
        """Get array disk information WITHOUT waking sleeping disks.

        This is the recommended method for getting disk status in automations
        or periodic polling, as it does NOT wake sleeping/standby disks.

        The array endpoint returns disk information including:
        - Disk state, name, device, size, status, type
        - Temperature (only for spinning disks, null/0 for standby)
        - isSpinning (True if disk is active, False if in standby)
        - Filesystem info (fsSize, fsUsed, fsFree, fsType)

        Returns:
            Dictionary with keys:
            - 'boot': Boot/flash device info (or None)
            - 'disks': List of data disks
            - 'parities': List of parity disks
            - 'caches': List of cache/pool disks

        Note:
            Temperature will be null/0 for disks in standby mode.
            Use the isSpinning field to check if a disk is active.
            This is the same approach used by Home Assistant integrations
            to avoid disrupting disk power management.

        """
        query_str = """
            query {
                array {
                    boot {
                        id name device size status type temp
                        fsSize fsUsed fsFree fsType
                    }
                    disks {
                        id idx name device size status type temp
                        fsSize fsUsed fsFree fsType isSpinning
                    }
                    parities {
                        id idx name device size status type temp isSpinning
                    }
                    caches {
                        id idx name device size status type temp
                        fsSize fsUsed fsFree fsType isSpinning
                    }
                }
            }
        """
        result = await self.query(query_str)
        array_data = result.get("array", {})
        return {
            "boot": array_data.get("boot"),
            "disks": list(array_data.get("disks", [])),
            "parities": list(array_data.get("parities", [])),
            "caches": list(array_data.get("caches", [])),
        }

    # =========================================================================
    # Parity History Methods
    # =========================================================================

    async def get_parity_history(self) -> list[dict[str, Any]]:
        """Get parity check history.

        Returns:
            List of parity check history entries.

        """
        query_str = """
            query {
                parityHistory {
                    date
                    duration
                    speed
                    status
                    errors
                }
            }
        """
        result = await self.query(query_str)
        return list(result.get("parityHistory", []))

    # =========================================================================
    # Registration Methods
    # =========================================================================

    async def get_registration(self) -> dict[str, Any]:
        """Get license registration information.

        Returns:
            Registration data including license type and state.

        """

        query_str = """
            query {
                registration {
                    id
                    type
                    state
                    expiration
                    updateExpiration
                }
            }
        """
        result = await self.query(query_str)
        return dict(result.get("registration", {}))

    async def typed_get_registration(self) -> Registration:
        """Get license registration as Pydantic model.

        Returns:
            Registration model with license information.

        """
        from unraid_api.models import Registration

        data = await self.get_registration()
        return Registration(**data)

    # =========================================================================
    # System Variables Methods
    # =========================================================================

    async def get_vars(self) -> dict[str, Any]:
        """Get system variables.

        Returns the unified system configuration from /var/local/emhttp/var.ini.
        Contains hostname, timezone, array state, share counts, and more.

        Returns:
            System vars dictionary with all configuration values.

        """
        query_str = """
            query {
                vars {
                    id
                    version
                    name
                    timeZone
                    comment
                    security
                    workgroup
                    domain
                    domainShort
                    maxArraysz
                    maxCachesz
                    sysModel
                    sysArraySlots
                    sysCacheSlots
                    sysFlashSlots
                    deviceCount
                    useSsl
                    port
                    portssl
                    localTld
                    bindMgt
                    useTelnet
                    porttelnet
                    useSsh
                    portssh
                    useNtp
                    ntpServer1
                    ntpServer2
                    ntpServer3
                    ntpServer4
                    hideDotFiles
                    localMaster
                    enableFruit
                    shareSmbEnabled
                    shareNfsEnabled
                    shareAfpEnabled
                    startArray
                    spindownDelay
                    safeMode
                    startMode
                    configValid
                    configError
                    flashGuid
                    flashProduct
                    flashVendor
                    regCheck
                    regFile
                    regGuid
                    regTy
                    regState
                    regTo
                    mdColor
                    mdNumDisks
                    mdNumDisabled
                    mdNumInvalid
                    mdNumMissing
                    mdResync
                    mdResyncAction
                    mdResyncPos
                    mdState
                    mdVersion
                    cacheNumDevices
                    fsState
                    fsProgress
                    fsCopyPrcnt
                    fsNumMounted
                    fsNumUnmountable
                    shareCount
                    shareSmbCount
                    shareNfsCount
                    shareAfpCount
                    shareMoverActive
                    csrfToken
                }
            }
        """
        result = await self.query(query_str)
        return dict(result.get("vars", {}))

    async def typed_get_vars(self) -> Vars:
        """Get system variables as a Pydantic model.

        Returns:
            Vars model with all system configuration.

        """
        from unraid_api.models import Vars

        data = await self.get_vars()
        return Vars(**data)

    # =========================================================================
    # Service Methods
    # =========================================================================

    async def get_services(self) -> list[dict[str, Any]]:
        """Get system services status.

        Returns:
            List of service data dictionaries.

        """
        query_str = """
            query {
                services {
                    id
                    name
                    online
                    uptime { timestamp }
                    version
                }
            }
        """
        result = await self.query(query_str)
        return list(result.get("services", []))

    async def typed_get_services(self) -> list[Service]:
        """Get system services as Pydantic models.

        Returns:
            List of Service models.

        """
        from unraid_api.models import Service

        services = await self.get_services()
        return [Service(**s) for s in services]

    # =========================================================================
    # Flash Drive Methods
    # =========================================================================

    async def get_flash(self) -> dict[str, Any]:
        """Get flash drive information.

        Returns:
            Flash drive data dictionary.

        """
        query_str = """
            query {
                flash {
                    id
                    vendor
                    product
                }
            }
        """
        result = await self.query(query_str)
        return dict(result.get("flash", {}))

    async def typed_get_flash(self) -> Flash:
        """Get flash drive as Pydantic model.

        Returns:
            Flash model with drive information.

        """
        from unraid_api.models import Flash

        data = await self.get_flash()
        return Flash(**data)

    # =========================================================================
    # Owner Methods
    # =========================================================================

    async def get_owner(self) -> dict[str, Any]:
        """Get owner/user information.

        Note: avatar and url fields are only available when signed into Unraid Connect.
        The API may return errors for these non-nullable fields if not signed in.

        Returns:
            Owner data dictionary.

        """
        query_str = """
            query {
                owner {
                    username
                }
            }
        """
        result = await self.query(query_str)
        return dict(result.get("owner", {}))

    async def typed_get_owner(self) -> Owner:
        """Get owner as Pydantic model.

        Returns:
            Owner model with user information.

        """
        from unraid_api.models import Owner

        data = await self.get_owner()
        return Owner(**data)

    # =========================================================================
    # Plugin Methods
    # =========================================================================

    async def get_plugins(self) -> list[dict[str, Any]]:
        """Get installed plugins.

        Returns:
            List of plugin data dictionaries.

        """
        query_str = """
            query {
                plugins {
                    name
                    version
                    hasApiModule
                    hasCliModule
                }
            }
        """
        result = await self.query(query_str)
        return list(result.get("plugins", []))

    async def typed_get_plugins(self) -> list[Plugin]:
        """Get installed plugins as Pydantic models.

        Returns:
            List of Plugin models.

        """
        from unraid_api.models import Plugin

        plugins = await self.get_plugins()
        return [Plugin(**p) for p in plugins]

    # =========================================================================
    # Docker Network Methods
    # =========================================================================

    async def get_docker_networks(self) -> list[dict[str, Any]]:
        """Get Docker networks.

        Returns:
            List of Docker network data dictionaries.

        """
        query_str = """
            query {
                docker {
                    networks {
                        id
                        name
                        created
                        scope
                        driver
                        enableIPv6
                        internal
                        attachable
                        ingress
                        configOnly
                    }
                }
            }
        """
        result = await self.query(query_str)
        return list(result.get("docker", {}).get("networks", []))

    async def typed_get_docker_networks(self) -> list[DockerNetwork]:
        """Get Docker networks as Pydantic models.

        Returns:
            List of DockerNetwork models.

        """
        from unraid_api.models import DockerNetwork

        networks = await self.get_docker_networks()
        return [DockerNetwork(**n) for n in networks]

    # =========================================================================
    # Log File Methods
    # =========================================================================

    async def get_log_files(self) -> list[dict[str, Any]]:
        """Get available log files.

        Returns:
            List of log file data dictionaries.

        """
        query_str = """
            query {
                logFiles {
                    name
                    path
                    size
                    modifiedAt
                }
            }
        """
        result = await self.query(query_str)
        return list(result.get("logFiles", []))

    async def typed_get_log_files(self) -> list[LogFile]:
        """Get available log files as Pydantic models.

        Returns:
            List of LogFile models.

        """
        from unraid_api.models import LogFile

        log_files = await self.get_log_files()
        return [LogFile(**lf) for lf in log_files]

    async def get_log_file(self, path: str, lines: int | None = None) -> dict[str, Any]:
        """Get contents of a specific log file.

        Args:
            path: Path to the log file.
            lines: Number of lines to return (optional).

        Returns:
            Log file content data.

        """
        query_str = """
            query GetLogFile($path: String!, $lines: Int) {
                logFile(path: $path, lines: $lines) {
                    path
                    content
                    totalLines
                    startLine
                }
            }
        """
        variables: dict[str, Any] = {"path": path}
        if lines is not None:
            variables["lines"] = lines
        result = await self.query(query_str, variables)
        return dict(result.get("logFile", {}))

    # =========================================================================
    # Cloud/Connect Methods
    # =========================================================================

    async def get_cloud(self) -> dict[str, Any]:
        """Get cloud settings information.

        Returns:
            Cloud settings data dictionary.

        """
        query_str = """
            query {
                cloud {
                    error
                    apiKey { valid error }
                    relay { status timeout error }
                    minigraphql { status timeout error }
                    cloud { status ip error }
                    allowedOrigins
                }
            }
        """
        result = await self.query(query_str)
        return dict(result.get("cloud", {}))

    async def typed_get_cloud(self) -> Cloud:
        """Get cloud settings as Pydantic model.

        Returns:
            Cloud model with settings information.

        """
        from unraid_api.models import Cloud

        data = await self.get_cloud()
        return Cloud(**data)

    async def get_connect(self) -> dict[str, Any]:
        """Get Unraid Connect information.

        Returns:
            Connect data dictionary.

        """
        query_str = """
            query {
                connect {
                    id
                    dynamicRemoteAccess {
                        enabledType
                        runningType
                        error
                    }
                }
            }
        """
        result = await self.query(query_str)
        return dict(result.get("connect", {}))

    async def typed_get_connect(self) -> Connect:
        """Get Unraid Connect as Pydantic model.

        Returns:
            Connect model with connection information.

        """
        from unraid_api.models import Connect

        data = await self.get_connect()
        return Connect(**data)

    async def get_remote_access(self) -> dict[str, Any]:
        """Get remote access configuration.

        Returns:
            Remote access data dictionary.

        """
        query_str = """
            query {
                remoteAccess {
                    accessType
                    forwardType
                    port
                }
            }
        """
        result = await self.query(query_str)
        return dict(result.get("remoteAccess", {}))

    async def typed_get_remote_access(self) -> RemoteAccess:
        """Get remote access as Pydantic model.

        Returns:
            RemoteAccess model with configuration.

        """
        from unraid_api.models import RemoteAccess

        data = await self.get_remote_access()
        return RemoteAccess(**data)

    # =========================================================================
    # Notification Mutation Methods
    # =========================================================================

    async def archive_notification(self, notification_id: str) -> dict[str, Any]:
        """Archive a notification.

        Args:
            notification_id: ID of the notification to archive.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation ArchiveNotification($id: PrefixedID!) {
                notifications {
                    archive(id: $id) {
                        id
                        title
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": notification_id})

    async def unarchive_notification(self, notification_id: str) -> dict[str, Any]:
        """Mark an archived notification as unread.

        Args:
            notification_id: ID of the notification to unarchive.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation UnarchiveNotification($id: PrefixedID!) {
                notifications {
                    unread(id: $id) {
                        id
                        title
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": notification_id})

    async def delete_notification(self, notification_id: str) -> dict[str, Any]:
        """Delete a notification.

        Args:
            notification_id: ID of the notification to delete.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation DeleteNotification($id: PrefixedID!) {
                notifications {
                    delete(id: $id)
                }
            }
        """
        return await self.mutate(mutation, {"id": notification_id})

    async def archive_all_notifications(self) -> dict[str, Any]:
        """Archive all unread notifications.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation ArchiveAllNotifications {
                notifications {
                    archiveAll
                }
            }
        """
        return await self.mutate(mutation)

    async def delete_all_notifications(self) -> dict[str, Any]:
        """Delete all archived notifications.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation DeleteAllNotifications {
                notifications {
                    deleteAll
                }
            }
        """
        return await self.mutate(mutation)

    # =========================================================================
    # VM Reset Method
    # =========================================================================

    async def reset_vm(self, vm_id: str) -> dict[str, Any]:
        """Reset a virtual machine (hard reset).

        Args:
            vm_id: VM ID to reset.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation ResetVM($id: PrefixedID!) {
                vm {
                    reset(id: $id)
                }
            }
        """
        return await self.mutate(mutation, {"id": vm_id})

    # =========================================================================
    # Array Disk Management Methods
    # =========================================================================

    async def add_array_disk(self, disk_id: str) -> dict[str, Any]:
        """Add a disk to the array.

        Args:
            disk_id: Disk ID to add.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation AddArrayDisk($id: PrefixedID!) {
                array {
                    addDisk(id: $id) {
                        id
                        name
                        status
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": disk_id})

    async def remove_array_disk(self, disk_id: str) -> dict[str, Any]:
        """Remove a disk from the array.

        Args:
            disk_id: Disk ID to remove.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation RemoveArrayDisk($id: PrefixedID!) {
                array {
                    removeDisk(id: $id) {
                        id
                        name
                        status
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": disk_id})

    async def clear_disk_stats(self, disk_id: str) -> dict[str, Any]:
        """Clear statistics for an array disk.

        Args:
            disk_id: Disk ID to clear statistics for.

        Returns:
            Mutation response data.

        """
        mutation = """
            mutation ClearDiskStats($id: PrefixedID!) {
                array {
                    clearStatistics(id: $id) {
                        id
                        name
                    }
                }
            }
        """
        return await self.mutate(mutation, {"id": disk_id})
