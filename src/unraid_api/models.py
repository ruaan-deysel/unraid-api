"""Pydantic models for Unraid GraphQL API responses."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    """Parse datetime from ISO format string or return datetime as-is.

    Args:
        value: ISO format string, datetime object, or None.

    Returns:
        Parsed datetime or None.

    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Python's fromisoformat doesn't handle trailing Z, normalize first
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(normalized)
    return None


# Reusable annotated type for datetime fields parsed from ISO format strings.
# Use this instead of repeating @field_validator("field", mode="before") on
# every datetime field.
ParsedDatetime = Annotated[datetime | None, BeforeValidator(_parse_datetime)]


def format_bytes(bytes_value: int | None) -> str | None:
    """Convert bytes to human-readable string.

    Args:
        bytes_value: Number of bytes, or None.

    Returns:
        Human-readable string (e.g., "1.5 GB") or None if input is None.

    """
    if bytes_value is None:
        return None
    if bytes_value == 0:
        return "0 B"

    units = ("B", "KB", "MB", "GB", "TB", "PB")
    exponent = min(int(math.log2(abs(bytes_value)) // 10), len(units) - 1)
    value = bytes_value / (1024**exponent)

    if value == int(value):
        return f"{int(value)} {units[exponent]}"
    return f"{value:.1f} {units[exponent]}"


def _format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string.

    Args:
        seconds: Duration in seconds.

    Returns:
        Human-readable string like "2 hours 15 minutes 30 seconds".

    """
    seconds = max(seconds, 0)

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes:
        parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
    if secs or not parts:
        parts.append(f"{secs} {'second' if secs == 1 else 'seconds'}")

    return " ".join(parts)


class UnraidBaseModel(BaseModel):
    """Base model that ignores unknown fields for forward compatibility."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# =============================================================================
# System Info Models
# =============================================================================


class InfoSystem(UnraidBaseModel):
    """System information (manufacturer, model, version, serial, UUID)."""

    uuid: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    version: str | None = None
    serial: str | None = None


class CpuPackages(UnraidBaseModel):
    """CPU package information (temperature, power consumption)."""

    temp: list[float] = []
    totalPower: float | None = None


class InfoCpu(UnraidBaseModel):
    """CPU information (brand, threads, cores, temperature, power)."""

    brand: str | None = None
    threads: int | None = None
    cores: int | None = None
    packages: CpuPackages = CpuPackages()


class InfoOs(UnraidBaseModel):
    """Operating system information (hostname, uptime, kernel)."""

    hostname: str | None = None
    uptime: ParsedDatetime = None
    kernel: str | None = None


class CoreVersions(UnraidBaseModel):
    """Core version information."""

    unraid: str | None = None
    api: str | None = None
    kernel: str | None = None


class InfoVersions(UnraidBaseModel):
    """Version information container."""

    core: CoreVersions = CoreVersions()


class SystemInfo(UnraidBaseModel):
    """Complete system information."""

    time: ParsedDatetime = None
    system: InfoSystem = InfoSystem()
    cpu: InfoCpu = InfoCpu()
    os: InfoOs = InfoOs()
    versions: InfoVersions = InfoVersions()


# =============================================================================
# Metrics Models
# =============================================================================


class CpuUtilization(UnraidBaseModel):
    """CPU utilization metrics."""

    percentTotal: float | None = None


class MemoryUtilization(UnraidBaseModel):
    """Memory utilization metrics."""

    total: int | None = None
    used: int | None = None
    free: int | None = None
    available: int | None = None
    percentTotal: float | None = None
    swapTotal: int | None = None
    swapUsed: int | None = None
    percentSwapTotal: float | None = None


class Metrics(UnraidBaseModel):
    """System metrics container."""

    cpu: CpuUtilization = CpuUtilization()
    memory: MemoryUtilization = MemoryUtilization()


# =============================================================================
# Array Models
# =============================================================================


class CapacityKilobytes(UnraidBaseModel):
    """Storage capacity in kilobytes."""

    total: int = 0
    used: int = 0
    free: int = 0


class ArrayCapacity(UnraidBaseModel):
    """Array capacity information."""

    kilobytes: CapacityKilobytes = CapacityKilobytes()

    @property
    def total_bytes(self) -> int:
        """Return total capacity in bytes."""
        return self.kilobytes.total * 1024

    @property
    def used_bytes(self) -> int:
        """Return used capacity in bytes."""
        return self.kilobytes.used * 1024

    @property
    def free_bytes(self) -> int:
        """Return free capacity in bytes."""
        return self.kilobytes.free * 1024

    @property
    def usage_percent(self) -> float:
        """Return usage percentage."""
        if self.kilobytes.total == 0:
            return 0.0
        return self.kilobytes.used / self.kilobytes.total * 100


class ParityCheck(UnraidBaseModel):
    """Parity check status."""

    status: str | None = None
    progress: int | None = None
    errors: int | None = None
    running: bool | None = None
    paused: bool | None = None
    speed: int | None = None
    elapsed: int | None = None  # Elapsed time in seconds
    estimated: int | None = None  # Estimated time remaining

    @property
    def is_running(self) -> bool:
        """Return True if the parity check is actively running or paused."""
        if self.status is None:
            return False
        return self.status.upper() in {"RUNNING", "PAUSED"}

    @property
    def has_problem(self) -> bool:
        """Return True if there are errors or the check has failed."""
        if self.status is not None and self.status.upper() == "FAILED":
            return True
        return bool(self.errors is not None and self.errors > 0)


class ArrayDisk(UnraidBaseModel):
    """Array disk information.

    This model represents disks as returned by the array endpoint,
    which does NOT wake sleeping disks. Use this for periodic polling.

    Note:
        - temp will be null/0 for disks in standby mode
        - isSpinning indicates if disk is active (True) or standby (False)
        - This is safe for Home Assistant integrations that poll frequently
        - On ZFS pools, fsUsed may be 0 or None; properties fall back to
          computing used space from fsSize - fsFree when available.

    """

    id: str
    idx: int | None = None  # Optional - boot device doesn't have idx
    device: str | None = None
    name: str | None = None
    type: str | None = None
    size: int | None = None
    fsSize: int | None = None
    fsUsed: int | None = None
    fsFree: int | None = None
    fsType: str | None = None  # Filesystem type (XFS, BTRFS, vfat, etc.)
    temp: int | None = None  # Temperature in Celsius (null when disk is standby)
    status: str | None = None
    isSpinning: bool | None = None  # True = active, False = standby/sleeping
    smartStatus: str | None = None  # Only available via physical disk query

    @property
    def is_standby(self) -> bool:
        """Return True if disk is in standby/sleeping mode."""
        return self.isSpinning is False

    @property
    def is_healthy(self) -> bool:
        """Return True if disk status indicates normal operation."""
        if self.status is None:
            return False
        return self.status.upper() == "DISK_OK"

    @property
    def size_bytes(self) -> int | None:
        """Return disk size in bytes."""
        return self.size * 1024 if self.size is not None else None

    @property
    def fs_size_bytes(self) -> int | None:
        """Return filesystem size in bytes."""
        return self.fsSize * 1024 if self.fsSize is not None else None

    @property
    def fs_used_bytes(self) -> int | None:
        """Return filesystem used space in bytes.

        Falls back to (fsSize - fsFree) when fsUsed is 0 or None,
        which is common on ZFS pools where the API reports fsUsed=0.
        """
        # If fsUsed is positive, use it directly
        if self.fsUsed is not None and self.fsUsed > 0:
            return self.fsUsed * 1024
        # Fallback: compute from fsSize - fsFree (ZFS workaround)
        if self.fsSize is not None and self.fsFree is not None:
            computed = self.fsSize - self.fsFree
            if computed >= 0:
                return computed * 1024
        # If fsUsed is explicitly 0 (not None), preserve that
        if self.fsUsed is not None:
            return self.fsUsed * 1024
        return None

    @property
    def fs_free_bytes(self) -> int | None:
        """Return filesystem free space in bytes."""
        return self.fsFree * 1024 if self.fsFree is not None else None

    @property
    def usage_percent(self) -> float | None:
        """Return disk usage percentage.

        Falls back to computing from fsSize and fsFree when fsUsed is
        0 or None (ZFS pool workaround).
        """
        if self.fsSize is None or self.fsSize == 0:
            return None

        # Use fsUsed directly if positive
        if self.fsUsed is not None and self.fsUsed > 0:
            return (self.fsUsed / self.fsSize) * 100

        # Fallback: compute from fsSize - fsFree
        if self.fsFree is not None:
            computed_used = self.fsSize - self.fsFree
            if computed_used >= 0:
                return (computed_used / self.fsSize) * 100

        return None


class UnraidArray(UnraidBaseModel):
    """Complete array information."""

    state: str | None = None
    capacity: ArrayCapacity = ArrayCapacity()
    parityCheckStatus: ParityCheck = ParityCheck()
    disks: list[ArrayDisk] = []
    parities: list[ArrayDisk] = []
    caches: list[ArrayDisk] = []
    boot: ArrayDisk | None = None


# =============================================================================
# Physical Disk Models (WARNING: Queries wake sleeping disks!)
# =============================================================================


class PhysicalDisk(UnraidBaseModel):
    """Physical disk information from the disks endpoint.

    WARNING: Querying physical disks WAKES SLEEPING DISKS!
    Use ArrayDisk (from get_array_disks) for disk info without wake.

    This model contains hardware-level disk information including SMART
    status, which requires disk access and will spin up any sleeping disk.

    """

    id: str
    device: str | None = None
    name: str | None = None
    vendor: str | None = None
    size: int | None = None  # Size in bytes
    type: str | None = None
    interfaceType: str | None = None  # SATA, SAS, NVMe, USB, etc.
    smartStatus: str | None = None  # OK, UNKNOWN, FAILING, etc.
    temperature: float | None = None  # Temperature in Celsius
    isSpinning: bool | None = None


# =============================================================================
# Docker Models
# =============================================================================


class ContainerPort(UnraidBaseModel):
    """Docker container port mapping."""

    ip: str | None = None
    privatePort: int | None = None
    publicPort: int | None = None
    type: str | None = None


class ContainerHostConfig(UnraidBaseModel):
    """Docker container host configuration."""

    networkMode: str | None = None


class DockerContainerStats(UnraidBaseModel):
    """Docker container resource statistics."""

    cpuPercent: float | None = None
    memoryUsage: int | None = None  # Memory in bytes
    memoryPercent: float | None = None
    networkRx: int | None = None  # Bytes received
    networkTx: int | None = None  # Bytes transmitted
    blockRead: int | None = None  # Bytes read from disk
    blockWrite: int | None = None  # Bytes written to disk


class DockerContainer(UnraidBaseModel):
    """Docker container information."""

    id: str
    name: str
    names: list[str] = []  # Container may have multiple names
    state: str | None = None
    status: str | None = None  # Status message (e.g., "Up 5 days")
    image: str | None = None
    imageId: str | None = None
    command: str | None = None
    created: int | None = None  # Unix timestamp
    sizeRootFs: int | None = None  # Total size of files in bytes
    labels: dict[str, Any] | None = None
    networkSettings: dict[str, Any] | None = None
    mounts: list[dict[str, Any]] | None = None
    webUiUrl: str | None = None
    iconUrl: str | None = None
    autoStart: bool | None = None
    isUpdateAvailable: bool | None = None
    isOrphaned: bool | None = None
    hostConfig: ContainerHostConfig | None = None
    ports: list[ContainerPort] = []
    stats: DockerContainerStats | None = None

    @property
    def is_running(self) -> bool:
        """Return True if the container is running."""
        if self.state is None:
            return False
        return self.state.lower() == "running"

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> DockerContainer:
        """Create DockerContainer from API response.

        Extracts name from the names array, removing leading slashes.

        Args:
            data: API response data for a container.

        Returns:
            DockerContainer instance with parsed data.

        """
        names = data.get("names", []) or []
        # Extract name from names array, removing leading slash
        name = names[0].lstrip("/") if names else data.get("id", "unknown")

        host_config = data.get("hostConfig")

        return cls(
            id=data.get("id", ""),
            name=name,
            names=names,
            state=data.get("state"),
            status=data.get("status"),
            image=data.get("image"),
            imageId=data.get("imageId"),
            command=data.get("command"),
            created=data.get("created"),
            sizeRootFs=data.get("sizeRootFs"),
            labels=data.get("labels"),
            networkSettings=data.get("networkSettings"),
            mounts=data.get("mounts"),
            webUiUrl=data.get("webUiUrl"),
            iconUrl=data.get("iconUrl"),
            autoStart=data.get("autoStart"),
            isUpdateAvailable=data.get("isUpdateAvailable"),
            isOrphaned=data.get("isOrphaned"),
            hostConfig=(ContainerHostConfig(**host_config) if host_config else None),
            ports=[ContainerPort(**p) for p in (data.get("ports") or [])],
            stats=(
                DockerContainerStats(**data["stats"]) if data.get("stats") else None
            ),
        )


class DockerNetwork(UnraidBaseModel):
    """Docker network information."""

    id: str
    name: str
    created: str | None = None
    scope: str | None = None
    driver: str | None = None
    enableIPv6: bool | None = None
    internal: bool | None = None
    attachable: bool | None = None
    ingress: bool | None = None
    configOnly: bool | None = None


# =============================================================================
# VM Models
# =============================================================================


class VmDomain(UnraidBaseModel):
    """Virtual machine domain information."""

    id: str
    name: str
    state: str | None = None
    memory: int | None = None  # Memory in bytes
    vcpu: int | None = None  # Number of virtual CPUs
    autostart: bool | None = None
    cpuMode: str | None = None
    iconUrl: str | None = None
    primaryGpu: str | None = None

    @property
    def is_running(self) -> bool:
        """Return True if the VM is running or idle."""
        if self.state is None:
            return False
        return self.state.lower() in {"running", "idle"}


# =============================================================================
# UPS Models
# =============================================================================


class UPSBattery(UnraidBaseModel):
    """UPS battery information."""

    chargeLevel: int | None = None
    estimatedRuntime: int | None = None
    health: str | None = None  # Battery health status

    @property
    def runtime_formatted(self) -> str | None:
        """Return estimated runtime as a human-readable string.

        Returns:
            Formatted string like "2 hours 15 minutes" or None if unavailable.

        """
        if self.estimatedRuntime is None:
            return None
        return _format_duration(self.estimatedRuntime)


class UPSPower(UnraidBaseModel):
    """UPS power information."""

    inputVoltage: float | None = None
    outputVoltage: float | None = None
    loadPercentage: float | None = None


class UPSDevice(UnraidBaseModel):
    """UPS device information."""

    id: str
    name: str
    model: str | None = None
    status: str | None = None
    battery: UPSBattery = UPSBattery()
    power: UPSPower = UPSPower()

    @property
    def is_connected(self) -> bool:
        """Return True if the UPS is connected and communicating."""
        if self.status is None:
            return False
        return self.status.upper() not in {"OFFLINE", "OFF"}

    def calculate_power_watts(self, nominal_power: int) -> float | None:
        """Calculate current power draw in watts.

        Args:
            nominal_power: The UPS nominal power capacity in watts
                (from user configuration, not available from the API).

        Returns:
            Power draw in watts rounded to 1 decimal, or None if
            load percentage is unavailable.

        """
        if self.power.loadPercentage is None:
            return None
        return round((self.power.loadPercentage / 100) * nominal_power, 1)


# =============================================================================
# Share Models
# =============================================================================


class Share(UnraidBaseModel):
    """User share information."""

    id: str
    name: str
    size: int | None = None  # Size in KB (often returns 0)
    used: int | None = None  # Used in KB
    free: int | None = None  # Free in KB

    @property
    def size_bytes(self) -> int | None:
        """Return share size in bytes (calculates from used+free if size=0)."""
        if self.size is not None and self.size > 0:
            return self.size * 1024
        if self.used is not None and self.free is not None:
            return (self.used + self.free) * 1024
        return None

    @property
    def used_bytes(self) -> int | None:
        """Return used space in bytes."""
        return self.used * 1024 if self.used is not None else None

    @property
    def free_bytes(self) -> int | None:
        """Return free space in bytes."""
        return self.free * 1024 if self.free is not None else None

    @property
    def usage_percent(self) -> float | None:
        """Return share usage percentage."""
        size = self.size_bytes
        used = self.used_bytes
        if size is None or size == 0 or used is None:
            return None
        return (used / size) * 100


# =============================================================================
# Notification Models
# =============================================================================


class Notification(UnraidBaseModel):
    """Unraid notification."""

    id: str
    title: str | None = None
    subject: str | None = None
    description: str | None = None
    importance: str | None = None
    link: str | None = None
    type: str | None = None
    timestamp: ParsedDatetime = None
    formattedTimestamp: str | None = None


class NotificationOverviewCounts(UnraidBaseModel):
    """Notification count by type."""

    info: int = 0
    warning: int = 0
    alert: int = 0
    total: int = 0


class NotificationOverview(UnraidBaseModel):
    """Notification overview with counts."""

    unread: NotificationOverviewCounts = NotificationOverviewCounts()
    archive: NotificationOverviewCounts = NotificationOverviewCounts()


# =============================================================================
# Physical Disk Models
# =============================================================================


class DiskPartition(UnraidBaseModel):
    """Physical disk partition."""

    name: str | None = None
    fsType: str | None = None
    size: int | None = None


# =============================================================================
# System Metrics Model (for Home Assistant integration)
# =============================================================================


class SystemMetrics(UnraidBaseModel):
    """System metrics for CPU, memory, and uptime monitoring.

    This model consolidates metrics data for Home Assistant sensor entities.
    Use get_system_metrics() to fetch this data efficiently.
    """

    # CPU metrics
    cpu_percent: float | None = None
    cpu_temperature: float | None = None  # First package temp (most common use)
    cpu_temperatures: list[float] = []  # All package temps (for multi-CPU)
    cpu_power: float | None = None  # Total power consumption in watts

    # Memory metrics
    memory_percent: float | None = None
    memory_total: int | None = None  # Total memory in bytes
    memory_used: int | None = None  # Used memory in bytes
    memory_free: int | None = None  # Free memory in bytes
    memory_available: int | None = None  # Available memory in bytes

    # Swap metrics
    swap_percent: float | None = None
    swap_total: int | None = None  # Total swap in bytes
    swap_used: int | None = None  # Used swap in bytes

    # Uptime
    uptime: ParsedDatetime = None  # System boot time

    @property
    def average_cpu_temperature(self) -> float | None:
        """Return the average CPU package temperature.

        Returns:
            Mean of all CPU package temperatures, or None if no data.

        """
        if not self.cpu_temperatures:
            return None
        return sum(self.cpu_temperatures) / len(self.cpu_temperatures)

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> SystemMetrics:
        """Create SystemMetrics from GraphQL response.

        Args:
            data: GraphQL response data containing metrics and info.

        Returns:
            SystemMetrics instance with parsed data.

        """
        metrics = data.get("metrics", {}) or {}
        cpu = metrics.get("cpu", {}) or {}
        memory = metrics.get("memory", {}) or {}
        info = data.get("info", {}) or {}
        os_info = info.get("os", {}) or {}

        # CPU temperature and power from info.cpu.packages
        cpu_info = info.get("cpu", {}) or {}
        packages = cpu_info.get("packages", {}) or {}
        temps = packages.get("temp", []) or []

        # Compute memory_used with fallback from total - available
        memory_used = memory.get("used")
        if memory_used is None:
            mem_total = memory.get("total")
            mem_available = memory.get("available")
            if mem_total is not None and mem_available is not None:
                memory_used = max(0, mem_total - mem_available)

        return cls(
            cpu_percent=cpu.get("percentTotal"),
            cpu_temperature=temps[0] if temps else None,
            cpu_temperatures=temps,
            cpu_power=packages.get("totalPower"),
            memory_percent=memory.get("percentTotal"),
            memory_total=memory.get("total"),
            memory_used=memory_used,
            memory_free=memory.get("free"),
            memory_available=memory.get("available"),
            swap_percent=memory.get("percentSwapTotal"),
            swap_total=memory.get("swapTotal"),
            swap_used=memory.get("swapUsed"),
            uptime=os_info.get("uptime"),
        )


# =============================================================================
# Server Info Model (for Home Assistant integration)
# =============================================================================


class ServerInfo(UnraidBaseModel):
    """Server information for device registration and identification.

    This model consolidates system, hardware, OS, and network information
    needed for Home Assistant device registration.
    """

    # Unique identification
    uuid: str | None = None
    hostname: str | None = None

    # Device info (for HA DeviceInfo)
    manufacturer: str = "Lime Technology"  # Always Lime Technology for Unraid
    model: str | None = None  # "Unraid {version}"
    sw_version: str | None = None  # Unraid version
    hw_version: str | None = None  # Kernel version
    serial_number: str | None = None

    # Hardware info (from system or baseboard fallback)
    hw_manufacturer: str | None = None
    hw_model: str | None = None

    # OS details
    os_distro: str | None = None
    os_release: str | None = None
    os_arch: str | None = None

    # API info
    api_version: str | None = None

    # Network/URLs
    lan_ip: str | None = None
    local_url: str | None = None
    remote_url: str | None = None

    # License
    license_type: str | None = None
    license_state: str | None = None

    # CPU info
    cpu_brand: str | None = None
    cpu_cores: int | None = None
    cpu_threads: int | None = None

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> ServerInfo:
        """Create ServerInfo from GraphQL response.

        Args:
            data: GraphQL response data containing info, server, and registration.

        Returns:
            ServerInfo instance with parsed data.

        """
        info = data.get("info", {})
        system = info.get("system", {}) or {}
        baseboard = info.get("baseboard", {}) or {}
        os_info = info.get("os", {}) or {}
        cpu = info.get("cpu", {}) or {}
        versions = info.get("versions", {}) or {}
        core_versions = versions.get("core", {}) or {}
        server = data.get("server", {}) or {}
        registration = data.get("registration", {}) or {}

        unraid_version = core_versions.get("unraid") or "Unknown"

        return cls(
            uuid=system.get("uuid"),
            hostname=os_info.get("hostname"),
            manufacturer="Lime Technology",
            model=f"Unraid {unraid_version}",
            sw_version=unraid_version,
            hw_version=os_info.get("kernel"),
            serial_number=system.get("serial") or baseboard.get("serial"),
            hw_manufacturer=system.get("manufacturer") or baseboard.get("manufacturer"),
            hw_model=system.get("model") or baseboard.get("model"),
            os_distro=os_info.get("distro"),
            os_release=os_info.get("release"),
            os_arch=os_info.get("arch"),
            api_version=core_versions.get("api"),
            lan_ip=server.get("lanip"),
            local_url=server.get("localurl"),
            remote_url=server.get("remoteurl"),
            license_type=registration.get("type"),
            license_state=registration.get("state"),
            cpu_brand=cpu.get("brand"),
            cpu_cores=cpu.get("cores"),
            cpu_threads=cpu.get("threads"),
        )


# =============================================================================
# Registration Models
# =============================================================================


class Registration(UnraidBaseModel):
    """Unraid license registration information."""

    id: str | None = None
    type: str | None = None  # License type (Basic, Plus, Pro, etc.)
    state: str | None = None  # License state
    expiration: str | None = None
    updateExpiration: str | None = None


# =============================================================================
# System Variables (Vars) Models
# =============================================================================


class Vars(UnraidBaseModel):
    """Unraid system variables (vars object).

    This represents the system configuration variables from /var/local/emhttp/var.ini.
    Contains many system settings including hostname, timezone, array state, etc.
    """

    id: str | None = None

    # Basic system info
    version: str | None = None
    name: str | None = None  # Machine hostname
    time_zone: str | None = Field(default=None, alias="timeZone")
    comment: str | None = None
    security: str | None = None
    workgroup: str | None = None
    domain: str | None = None
    domain_short: str | None = Field(default=None, alias="domainShort")

    # Array configuration
    max_arraysz: int | None = Field(default=None, alias="maxArraysz")
    max_cachesz: int | None = Field(default=None, alias="maxCachesz")
    sys_model: str | None = Field(default=None, alias="sysModel")
    sys_array_slots: int | None = Field(default=None, alias="sysArraySlots")
    sys_cache_slots: int | None = Field(default=None, alias="sysCacheSlots")
    sys_flash_slots: int | None = Field(default=None, alias="sysFlashSlots")
    device_count: int | None = Field(default=None, alias="deviceCount")

    # Network/services
    use_ssl: bool | None = Field(default=None, alias="useSsl")
    port: int | None = None  # HTTP port
    portssl: int | None = None  # HTTPS port
    local_tld: str | None = Field(default=None, alias="localTld")
    bind_mgt: bool | None = Field(default=None, alias="bindMgt")
    use_telnet: bool | None = Field(default=None, alias="useTelnet")
    port_telnet: int | None = Field(default=None, alias="porttelnet")
    use_ssh: bool | None = Field(default=None, alias="useSsh")
    port_ssh: int | None = Field(default=None, alias="portssh")

    # NTP settings
    use_ntp: bool | None = Field(default=None, alias="useNtp")
    ntp_server1: str | None = Field(default=None, alias="ntpServer1")
    ntp_server2: str | None = Field(default=None, alias="ntpServer2")
    ntp_server3: str | None = Field(default=None, alias="ntpServer3")
    ntp_server4: str | None = Field(default=None, alias="ntpServer4")

    # File sharing settings
    hide_dot_files: bool | None = Field(default=None, alias="hideDotFiles")
    local_master: bool | None = Field(default=None, alias="localMaster")
    enable_fruit: str | None = Field(default=None, alias="enableFruit")
    share_smb_enabled: bool | None = Field(default=None, alias="shareSmbEnabled")
    share_nfs_enabled: bool | None = Field(default=None, alias="shareNfsEnabled")
    share_afp_enabled: bool | None = Field(default=None, alias="shareAfpEnabled")

    # Array state
    start_array: bool | None = Field(default=None, alias="startArray")
    spindown_delay: str | None = Field(default=None, alias="spindownDelay")
    safe_mode: bool | None = Field(default=None, alias="safeMode")
    start_mode: str | None = Field(default=None, alias="startMode")
    config_valid: bool | None = Field(default=None, alias="configValid")
    config_error: str | None = Field(default=None, alias="configError")

    # Flash info (in vars)
    flash_guid: str | None = Field(default=None, alias="flashGuid")
    flash_product: str | None = Field(default=None, alias="flashProduct")
    flash_vendor: str | None = Field(default=None, alias="flashVendor")

    # Registration info (in vars)
    reg_check: str | None = Field(default=None, alias="regCheck")
    reg_file: str | None = Field(default=None, alias="regFile")
    reg_guid: str | None = Field(default=None, alias="regGuid")
    reg_ty: str | None = Field(default=None, alias="regTy")
    reg_state: str | None = Field(default=None, alias="regState")
    reg_to: str | None = Field(default=None, alias="regTo")  # Registration owner

    # Array/disk state
    md_color: str | None = Field(default=None, alias="mdColor")
    md_num_disks: int | None = Field(default=None, alias="mdNumDisks")
    md_num_disabled: int | None = Field(default=None, alias="mdNumDisabled")
    md_num_invalid: int | None = Field(default=None, alias="mdNumInvalid")
    md_num_missing: int | None = Field(default=None, alias="mdNumMissing")
    md_resync: int | None = Field(default=None, alias="mdResync")
    md_resync_action: str | None = Field(default=None, alias="mdResyncAction")
    md_resync_pos: str | None = Field(default=None, alias="mdResyncPos")
    md_state: str | None = Field(default=None, alias="mdState")
    md_version: str | None = Field(default=None, alias="mdVersion")

    # Cache state
    cache_num_devices: int | None = Field(default=None, alias="cacheNumDevices")

    # Filesystem state
    fs_state: str | None = Field(default=None, alias="fsState")
    fs_progress: str | None = Field(default=None, alias="fsProgress")
    fs_copy_prcnt: int | None = Field(default=None, alias="fsCopyPrcnt")
    fs_num_mounted: int | None = Field(default=None, alias="fsNumMounted")
    fs_num_unmountable: int | None = Field(default=None, alias="fsNumUnmountable")

    # Share counts
    share_count: int | None = Field(default=None, alias="shareCount")
    share_smb_count: int | None = Field(default=None, alias="shareSmbCount")
    share_nfs_count: int | None = Field(default=None, alias="shareNfsCount")
    share_afp_count: int | None = Field(default=None, alias="shareAfpCount")
    share_mover_active: bool | None = Field(default=None, alias="shareMoverActive")

    # Security
    csrf_token: str | None = Field(default=None, alias="csrfToken")


# =============================================================================
# Service Models
# =============================================================================


class ServiceUptime(UnraidBaseModel):
    """Service uptime information."""

    timestamp: str | None = None


class Service(UnraidBaseModel):
    """System service information."""

    id: str
    name: str
    online: bool | None = None
    uptime: ServiceUptime | None = None
    version: str | None = None


# =============================================================================
# Flash Drive Models
# =============================================================================


class Flash(UnraidBaseModel):
    """Flash drive information."""

    id: str
    product: str | None = None
    vendor: str | None = None


# =============================================================================
# Owner Models
# =============================================================================


class Owner(UnraidBaseModel):
    """Owner/user information."""

    username: str
    avatar: str | None = None
    url: str | None = None


# =============================================================================
# Plugin Models
# =============================================================================


class Plugin(UnraidBaseModel):
    """Plugin information from the Unraid API.

    Attributes:
        name: The name of the plugin package.
        version: The version of the plugin package.
        hasApiModule: Whether the plugin has an API module.
        hasCliModule: Whether the plugin has a CLI module.

    """

    name: str
    version: str
    hasApiModule: bool | None = None
    hasCliModule: bool | None = None


# =============================================================================
# Log File Models
# =============================================================================


class LogFile(UnraidBaseModel):
    """Log file information.

    Attributes:
        name: Name of the log file.
        path: Full path to the log file.
        size: Size of the log file in bytes.
        modifiedAt: Last modified timestamp.

    """

    name: str
    path: str
    size: int | None = None
    modifiedAt: str | None = None


class LogFileContent(UnraidBaseModel):
    """Log file content.

    Attributes:
        path: Path to the log file.
        content: Content of the log file.
        totalLines: Total number of lines in the file.
        startLine: Starting line number of the content (1-indexed).

    """

    path: str
    content: str | None = None
    totalLines: int | None = None
    startLine: int | None = None


# =============================================================================
# Cloud/Connect Models
# =============================================================================


class ApiKeyResponse(UnraidBaseModel):
    """API key response information.

    Attributes:
        valid: Whether the API key is valid.
        error: Any error message.

    """

    valid: bool | None = None
    error: str | None = None


class CloudResponse(UnraidBaseModel):
    """Cloud response information."""

    status: str
    ip: str | None = None
    error: str | None = None


class RelayResponse(UnraidBaseModel):
    """Relay response information."""

    status: str
    timeout: str | None = None
    error: str | None = None


class MinigraphqlResponse(UnraidBaseModel):
    """Minigraphql response information.

    Attributes:
        status: Status of minigraphql (PRE_INIT, CONNECTING, CONNECTED, etc).
        timeout: Timeout value.
        error: Any error message.

    """

    status: str | None = None
    timeout: int | None = None
    error: str | None = None


class Cloud(UnraidBaseModel):
    """Cloud settings information.

    Attributes:
        error: Any error message.
        apiKey: API key response details.
        relay: Relay connection status.
        minigraphql: Minigraphql connection status.
        cloud: Cloud connection status.
        allowedOrigins: List of allowed origins.

    """

    error: str | None = None
    apiKey: ApiKeyResponse | None = None
    relay: RelayResponse | None = None
    minigraphql: MinigraphqlResponse | None = None
    cloud: CloudResponse | None = None
    allowedOrigins: list[str] = []


class DynamicRemoteAccessStatus(UnraidBaseModel):
    """Dynamic remote access status.

    Attributes:
        enabledType: The type of dynamic remote access enabled.
        runningType: The type of dynamic remote access currently running.
        error: Any error message.

    """

    enabledType: str | None = None
    runningType: str | None = None
    error: str | None = None


class Connect(UnraidBaseModel):
    """Unraid Connect information.

    Attributes:
        id: Connect node ID.
        dynamicRemoteAccess: Dynamic remote access status.

    """

    id: str | None = None
    dynamicRemoteAccess: DynamicRemoteAccessStatus | None = None


class RemoteAccess(UnraidBaseModel):
    """Remote access configuration.

    Attributes:
        accessType: The type of WAN access (DYNAMIC, ALWAYS, DISABLED).
        forwardType: The type of port forwarding (UPNP, STATIC).
        port: The port used for remote access.

    """

    accessType: str | None = None
    forwardType: str | None = None
    port: int | None = None


# =============================================================================
# User & API Key Models
# =============================================================================


class Permission(UnraidBaseModel):
    """API key or user permission.

    Attributes:
        resource: The resource this permission applies to.
        actions: List of allowed actions on the resource.

    """

    resource: str
    actions: list[str] = []


class UserAccount(UnraidBaseModel):
    """Unraid user account information.

    Attributes:
        id: Unique user account ID.
        name: The name of the user account.
        description: Description of the user account.
        roles: List of roles assigned to the user.
        permissions: Optional list of permissions.

    """

    id: str
    name: str
    description: str | None = None
    roles: list[str] = []
    permissions: list[Permission] | None = None


class ApiKey(UnraidBaseModel):
    """API key information.

    Attributes:
        id: Unique API key ID (PrefixedID format).
        key: The API key value (only returned on create).
        name: Display name for the API key.
        description: Optional description.
        roles: List of roles assigned to this key.
        createdAt: ISO timestamp of when the key was created.
        permissions: List of permissions for this key.

    """

    id: str
    key: str | None = None
    name: str
    description: str | None = None
    roles: list[str] = []
    createdAt: str | None = None
    permissions: list[Permission] | None = None


# =============================================================================
# Docker Container Log Models
# =============================================================================


# =============================================================================
# Version Info Model
# =============================================================================


class VersionInfo(UnraidBaseModel):
    """Server version information.

    Attributes:
        api: The API version string.
        unraid: The Unraid OS version string.

    """

    api: str = "unknown"
    unraid: str = "unknown"


# =============================================================================
# Parity History Model
# =============================================================================


def _parse_parity_date(value: str | int | float | datetime | None) -> datetime | None:
    """Parse a parity history date from various formats.

    Handles ISO strings, epoch timestamps (int/float), datetime objects, and None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, int | float):
        from datetime import UTC

        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        # Try ISO format first
        try:
            normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass
        # Try epoch string
        try:
            from datetime import UTC

            return datetime.fromtimestamp(float(value), tz=UTC)
        except (ValueError, OSError):
            pass
    return None


ParityDate = Annotated[datetime | None, BeforeValidator(_parse_parity_date)]


class ParityHistoryEntry(UnraidBaseModel):
    """A single parity check history entry.

    Attributes:
        date: When the parity check occurred.
        duration: Duration in seconds.
        speed: Speed of the parity check.
        status: Result status of the check.
        errors: Number of errors found.

    """

    date: ParityDate = None
    duration: int | None = None
    speed: str | int | None = None
    status: str | None = None
    errors: int | None = None

    @property
    def duration_formatted(self) -> str | None:
        """Return duration as a human-readable string.

        Returns:
            Formatted string like "2 hours 15 minutes 30 seconds",
            or None if duration is unavailable.

        """
        if self.duration is None:
            return None
        return _format_duration(self.duration)


# =============================================================================
# Docker Container Log Models
# =============================================================================


class DockerContainerLogLine(UnraidBaseModel):
    """A single line from a Docker container log.

    Attributes:
        timestamp: Timestamp of the log entry.
        message: Log message content.

    """

    timestamp: str
    message: str


class DockerContainerLogs(UnraidBaseModel):
    """Docker container log retrieval result.

    Attributes:
        containerId: The container ID the logs belong to.
        lines: List of log lines.
        cursor: Cursor for pagination (DateTime).

    """

    containerId: str | None = None
    lines: list[DockerContainerLogLine] = []
    cursor: str | None = None
