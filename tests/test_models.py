"""Tests for Pydantic models."""

from __future__ import annotations

from datetime import UTC, datetime

from unraid_api.models import (
    ArrayCapacity,
    ArrayDisk,
    CapacityKilobytes,
    DockerContainer,
    InfoOs,
    Notification,
    PhysicalDisk,
    Share,
    UnraidArray,
)


class TestDatetimeParsing:
    """Tests for datetime parsing in models."""

    def test_parse_iso_datetime_with_z(self) -> None:
        """Test parsing ISO datetime with Z suffix."""
        os_info = InfoOs(uptime="2024-01-15T10:30:00Z")

        assert os_info.uptime is not None
        assert os_info.uptime.year == 2024
        assert os_info.uptime.month == 1
        assert os_info.uptime.day == 15

    def test_parse_iso_datetime_with_offset(self) -> None:
        """Test parsing ISO datetime with timezone offset."""
        os_info = InfoOs(uptime="2024-01-15T10:30:00+00:00")

        assert os_info.uptime is not None
        assert os_info.uptime.year == 2024

    def test_parse_none_datetime(self) -> None:
        """Test parsing None datetime."""
        os_info = InfoOs(uptime=None)

        assert os_info.uptime is None

    def test_parse_datetime_object(self) -> None:
        """Test passing datetime object directly."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        os_info = InfoOs(uptime=dt)

        assert os_info.uptime == dt


class TestArrayCapacity:
    """Tests for ArrayCapacity model."""

    def test_capacity_properties(self) -> None:
        """Test capacity byte conversion properties."""
        capacity = ArrayCapacity(
            kilobytes=CapacityKilobytes(total=1000, used=400, free=600)
        )

        assert capacity.total_bytes == 1024000
        assert capacity.used_bytes == 409600
        assert capacity.free_bytes == 614400

    def test_usage_percent(self) -> None:
        """Test usage percentage calculation."""
        capacity = ArrayCapacity(
            kilobytes=CapacityKilobytes(total=1000, used=400, free=600)
        )

        assert capacity.usage_percent == 40.0

    def test_usage_percent_zero_total(self) -> None:
        """Test usage percentage with zero total."""
        capacity = ArrayCapacity(kilobytes=CapacityKilobytes(total=0, used=0, free=0))

        assert capacity.usage_percent == 0.0


class TestArrayDisk:
    """Tests for ArrayDisk model."""

    def test_disk_with_required_fields(self) -> None:
        """Test disk creation with required fields only."""
        disk = ArrayDisk(id="disk:1")

        assert disk.id == "disk:1"
        assert disk.name is None
        assert disk.temp is None

    def test_disk_with_all_fields(self) -> None:
        """Test disk creation with all fields."""
        disk = ArrayDisk(
            id="disk:1",
            idx=1,
            device="sda",
            name="Disk 1",
            type="DATA",
            size=4000000000,
            fsSize=3900000000,
            fsUsed=1000000000,
            fsFree=2900000000,
            fsType="XFS",
            temp=35,
            status="DISK_OK",
            isSpinning=True,
            smartStatus="PASSED",
        )

        assert disk.id == "disk:1"
        assert disk.idx == 1
        assert disk.name == "Disk 1"
        assert disk.temp == 35
        assert disk.isSpinning is True

    def test_disk_is_standby_spinning(self) -> None:
        """Test is_standby property when disk is spinning."""
        disk = ArrayDisk(id="disk:1", isSpinning=True)
        assert disk.is_standby is False

    def test_disk_is_standby_sleeping(self) -> None:
        """Test is_standby property when disk is in standby."""
        disk = ArrayDisk(id="disk:1", isSpinning=False)
        assert disk.is_standby is True

    def test_disk_is_standby_none(self) -> None:
        """Test is_standby property when isSpinning is None."""
        disk = ArrayDisk(id="disk:1", isSpinning=None)
        # When isSpinning is None, is_standby should be False (not certain)
        assert disk.is_standby is False

    def test_disk_byte_properties(self) -> None:
        """Test disk byte conversion properties."""
        disk = ArrayDisk(
            id="disk:1",
            size=1000,
            fsSize=900,
            fsUsed=300,
            fsFree=600,
        )

        assert disk.size_bytes == 1024000
        assert disk.fs_size_bytes == 921600
        assert disk.fs_used_bytes == 307200
        assert disk.fs_free_bytes == 614400

    def test_disk_usage_percent(self) -> None:
        """Test disk usage percentage."""
        disk = ArrayDisk(
            id="disk:1",
            fsSize=1000,
            fsUsed=250,
        )

        assert disk.usage_percent == 25.0

    def test_disk_usage_percent_none_values(self) -> None:
        """Test disk usage percentage with None values."""
        disk = ArrayDisk(id="disk:1")

        assert disk.usage_percent is None


class TestDockerContainer:
    """Tests for DockerContainer model."""

    def test_container_required_fields(self) -> None:
        """Test container with required fields."""
        container = DockerContainer(id="container:abc123", name="plex")

        assert container.id == "container:abc123"
        assert container.name == "plex"
        assert container.state is None
        assert container.ports == []

    def test_container_with_all_fields(self) -> None:
        """Test container with all fields."""
        container = DockerContainer(
            id="container:abc123",
            name="plex",
            state="RUNNING",
            image="plexinc/pms-docker:latest",
            webUiUrl="http://192.168.1.100:32400/web",
            iconUrl="/icons/plex.png",
        )

        assert container.state == "RUNNING"
        assert container.image == "plexinc/pms-docker:latest"


class TestShare:
    """Tests for Share model."""

    def test_share_size_from_size_field(self) -> None:
        """Test share size calculation from size field."""
        share = Share(id="share:1", name="appdata", size=1000, used=400, free=600)

        assert share.size_bytes == 1024000

    def test_share_size_from_used_free(self) -> None:
        """Test share size calculation from used+free when size is 0."""
        share = Share(id="share:1", name="appdata", size=0, used=400, free=600)

        assert share.size_bytes == 1024000

    def test_share_usage_percent(self) -> None:
        """Test share usage percentage."""
        share = Share(id="share:1", name="appdata", size=1000, used=250, free=750)

        assert share.usage_percent == 25.0

    def test_share_used_bytes(self) -> None:
        """Test share used_bytes property."""
        share = Share(id="share:1", name="appdata", used=500)
        assert share.used_bytes == 512000

    def test_share_free_bytes(self) -> None:
        """Test share free_bytes property."""
        share = Share(id="share:1", name="appdata", free=500)
        assert share.free_bytes == 512000

    def test_share_size_bytes_all_none(self) -> None:
        """Test share size_bytes when all values are None."""
        share = Share(id="share:1", name="appdata")
        assert share.size_bytes is None

    def test_share_usage_percent_zero_size(self) -> None:
        """Test share usage_percent when size is zero."""
        share = Share(id="share:1", name="appdata", size=0, used=0, free=0)
        # When size=0 and used=0 and free=0, size_bytes = 0
        assert share.usage_percent is None

    def test_share_usage_percent_none_used(self) -> None:
        """Test share usage_percent when used is None."""
        share = Share(id="share:1", name="appdata", size=1000)
        assert share.usage_percent is None

    def test_share_used_bytes_none(self) -> None:
        """Test share used_bytes when used is None."""
        share = Share(id="share:1", name="appdata")
        assert share.used_bytes is None

    def test_share_free_bytes_none(self) -> None:
        """Test share free_bytes when free is None."""
        share = Share(id="share:1", name="appdata")
        assert share.free_bytes is None


class TestUnraidArray:
    """Tests for UnraidArray model."""

    def test_array_defaults(self) -> None:
        """Test array with default values."""
        array = UnraidArray(capacity=ArrayCapacity())

        assert array.state is None
        assert array.disks == []
        assert array.parities == []
        assert array.caches == []
        assert array.boot is None

    def test_array_with_disks(self) -> None:
        """Test array with disk list."""
        array = UnraidArray(
            state="STARTED",
            capacity=ArrayCapacity(),
            disks=[
                ArrayDisk(id="disk:1", name="Disk 1"),
                ArrayDisk(id="disk:2", name="Disk 2"),
            ],
        )

        assert array.state == "STARTED"
        assert len(array.disks) == 2
        assert array.disks[0].name == "Disk 1"


class TestNotification:
    """Tests for Notification model."""

    def test_notification_timestamp_parsing(self) -> None:
        """Test notification timestamp parsing."""
        notification = Notification(
            id="notif:1",
            title="Test",
            timestamp="2024-01-15T10:30:00Z",
        )

        assert notification.timestamp is not None
        assert notification.timestamp.year == 2024

    def test_notification_with_all_fields(self) -> None:
        """Test notification with all fields."""
        notification = Notification(
            id="notif:1",
            title="Parity Check Complete",
            subject="Parity check completed successfully",
            description="No errors found",
            importance="INFO",
            type="UNREAD",
        )

        assert notification.title == "Parity Check Complete"
        assert notification.importance == "INFO"


class TestPhysicalDisk:
    """Tests for PhysicalDisk model."""

    def test_physical_disk_required_fields(self) -> None:
        """Test physical disk with required fields only."""
        disk = PhysicalDisk(id="disk:sda")
        assert disk.id == "disk:sda"
        assert disk.device is None
        assert disk.smartStatus is None

    def test_physical_disk_with_all_fields(self) -> None:
        """Test physical disk with all fields."""
        disk = PhysicalDisk(
            id="disk:sda",
            device="/dev/sda",
            name="WDC WD140EDFZ-11A0VA0",
            vendor="Western Digital",
            size=14000519643136,  # 14TB in bytes
            type="HDD",
            interfaceType="SATA",
            smartStatus="OK",
            temperature=35.0,
            isSpinning=True,
        )

        assert disk.id == "disk:sda"
        assert disk.vendor == "Western Digital"
        assert disk.interfaceType == "SATA"
        assert disk.smartStatus == "OK"
        assert disk.temperature == 35.0
        assert disk.isSpinning is True


class TestForwardCompatibility:
    """Tests for forward compatibility (ignoring unknown fields)."""

    def test_ignores_unknown_fields(self) -> None:
        """Test that unknown fields are ignored."""
        disk = ArrayDisk(
            id="disk:1",
            name="Disk 1",
            unknown_field="should be ignored",  # type: ignore[call-arg]
            another_unknown=123,  # type: ignore[call-arg]
        )

        assert disk.id == "disk:1"
        assert disk.name == "Disk 1"
        assert not hasattr(disk, "unknown_field")
