"""Pydantic models for Unraid GraphQL API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


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
    uptime: datetime | None = None
    kernel: str | None = None

    @field_validator("uptime", mode="before")
    @classmethod
    def parse_uptime(cls, value: str | datetime | None) -> datetime | None:
        """Parse uptime from ISO format string."""
        return _parse_datetime(value)


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

    time: datetime | None = None
    system: InfoSystem = InfoSystem()
    cpu: InfoCpu = InfoCpu()
    os: InfoOs = InfoOs()
    versions: InfoVersions = InfoVersions()

    @field_validator("time", mode="before")
    @classmethod
    def parse_time(cls, value: str | datetime | None) -> datetime | None:
        """Parse time from ISO format string."""
        return _parse_datetime(value)


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


class ArrayDisk(UnraidBaseModel):
    """Array disk information.

    This model represents disks as returned by the array endpoint,
    which does NOT wake sleeping disks. Use this for periodic polling.

    Note:
        - temp will be null/0 for disks in standby mode
        - isSpinning indicates if disk is active (True) or standby (False)
        - This is safe for Home Assistant integrations that poll frequently

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
    def size_bytes(self) -> int | None:
        """Return disk size in bytes."""
        return self.size * 1024 if self.size is not None else None

    @property
    def fs_size_bytes(self) -> int | None:
        """Return filesystem size in bytes."""
        return self.fsSize * 1024 if self.fsSize is not None else None

    @property
    def fs_used_bytes(self) -> int | None:
        """Return filesystem used space in bytes."""
        return self.fsUsed * 1024 if self.fsUsed is not None else None

    @property
    def fs_free_bytes(self) -> int | None:
        """Return filesystem free space in bytes."""
        return self.fsFree * 1024 if self.fsFree is not None else None

    @property
    def usage_percent(self) -> float | None:
        """Return disk usage percentage."""
        if self.fsSize is None or self.fsSize == 0 or self.fsUsed is None:
            return None
        return (self.fsUsed / self.fsSize) * 100


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
    webUiUrl: str | None = None
    iconUrl: str | None = None
    autoStart: bool | None = None
    isUpdateAvailable: bool | None = None
    isOrphaned: bool | None = None
    ports: list[ContainerPort] = []
    stats: DockerContainerStats | None = None


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


# =============================================================================
# UPS Models
# =============================================================================


class UPSBattery(UnraidBaseModel):
    """UPS battery information."""

    chargeLevel: int | None = None
    estimatedRuntime: int | None = None


class UPSPower(UnraidBaseModel):
    """UPS power information."""

    inputVoltage: float | None = None
    outputVoltage: float | None = None
    loadPercentage: float | None = None


class UPSDevice(UnraidBaseModel):
    """UPS device information."""

    id: str
    name: str
    status: str | None = None
    battery: UPSBattery = UPSBattery()
    power: UPSPower = UPSPower()


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
    timestamp: datetime | None = None
    formattedTimestamp: str | None = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value: str | datetime | None) -> datetime | None:
        """Parse timestamp from ISO format string."""
        return _parse_datetime(value)


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
# Response Type Aliases
# =============================================================================

# Type aliases for API response data
SystemInfoResponse = dict[str, Any]
ArrayResponse = dict[str, Any]
ContainersResponse = dict[str, Any]
VmsResponse = dict[str, Any]
UpsResponse = dict[str, Any]
SharesResponse = dict[str, Any]
NotificationsResponse = dict[str, Any]
DisksResponse = dict[str, Any]
