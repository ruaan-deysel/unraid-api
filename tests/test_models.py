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


class TestServerInfo:
    """Tests for ServerInfo model."""

    def test_server_info_default_values(self) -> None:
        """Test ServerInfo with default values."""
        from unraid_api.models import ServerInfo

        info = ServerInfo()

        assert info.uuid is None
        assert info.hostname is None
        assert info.manufacturer == "Lime Technology"
        assert info.model is None
        assert info.sw_version is None
        assert info.hw_version is None
        assert info.serial_number is None
        assert info.api_version is None
        assert info.lan_ip is None

    def test_server_info_with_all_fields(self) -> None:
        """Test ServerInfo with all fields populated."""
        from unraid_api.models import ServerInfo

        info = ServerInfo(
            uuid="abc123-def456",
            hostname="Tower",
            manufacturer="Lime Technology",
            model="Unraid 7.2.0",
            sw_version="7.2.0",
            hw_version="6.1.38-Unraid",
            serial_number="ABC123",
            hw_manufacturer="ASUS",
            hw_model="Z690",
            os_distro="Unraid",
            os_release="7.2.0",
            os_arch="x64",
            api_version="4.29.2",
            lan_ip="192.168.1.100",
            local_url="http://192.168.1.100",
            remote_url="https://myserver.myunraid.net",
            license_type="Pro",
            license_state="valid",
            cpu_brand="Intel Core i7-12700K",
            cpu_cores=12,
            cpu_threads=20,
        )

        assert info.uuid == "abc123-def456"
        assert info.hostname == "Tower"
        assert info.manufacturer == "Lime Technology"
        assert info.model == "Unraid 7.2.0"
        assert info.sw_version == "7.2.0"
        assert info.hw_version == "6.1.38-Unraid"
        assert info.serial_number == "ABC123"
        assert info.hw_manufacturer == "ASUS"
        assert info.hw_model == "Z690"
        assert info.os_distro == "Unraid"
        assert info.os_release == "7.2.0"
        assert info.os_arch == "x64"
        assert info.api_version == "4.29.2"
        assert info.lan_ip == "192.168.1.100"
        assert info.local_url == "http://192.168.1.100"
        assert info.remote_url == "https://myserver.myunraid.net"
        assert info.license_type == "Pro"
        assert info.license_state == "valid"
        assert info.cpu_brand == "Intel Core i7-12700K"
        assert info.cpu_cores == 12
        assert info.cpu_threads == 20

    def test_from_response_full_data(self) -> None:
        """Test from_response with complete GraphQL response."""
        from unraid_api.models import ServerInfo

        response = {
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

        info = ServerInfo.from_response(response)

        assert info.uuid == "abc123-def456"
        assert info.hostname == "Tower"
        assert info.manufacturer == "Lime Technology"
        assert info.model == "Unraid 7.2.0"
        assert info.sw_version == "7.2.0"
        assert info.hw_version == "6.1.38-Unraid"
        assert info.serial_number == "SYS123"
        assert info.hw_manufacturer == "Dell Inc."
        assert info.hw_model == "PowerEdge R730"
        assert info.os_distro == "Unraid"
        assert info.os_release == "7.2.0"
        assert info.os_arch == "x64"
        assert info.api_version == "4.29.2"
        assert info.lan_ip == "192.168.1.100"
        assert info.local_url == "http://192.168.1.100"
        assert info.remote_url == "https://myserver.myunraid.net"
        assert info.license_type == "Pro"
        assert info.license_state == "valid"
        assert info.cpu_brand == "Intel Xeon E5-2680"
        assert info.cpu_cores == 12
        assert info.cpu_threads == 24

    def test_from_response_baseboard_fallback(self) -> None:
        """Test from_response falls back to baseboard when system info is missing."""
        from unraid_api.models import ServerInfo

        response = {
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
                    "hostname": "Tower",
                    "distro": "Unraid",
                    "release": "7.2.0",
                    "kernel": "6.1.38-Unraid",
                    "arch": "x64",
                },
                "cpu": {
                    "brand": "Intel Core i7",
                    "cores": 8,
                    "threads": 16,
                },
                "versions": {"core": {"unraid": "7.2.0", "api": "4.29.2"}},
            },
            "server": {"lanip": "192.168.1.100"},
            "registration": {"type": "Basic", "state": "valid"},
        }

        info = ServerInfo.from_response(response)

        # Should fall back to baseboard values
        assert info.hw_manufacturer == "ASUS"
        assert info.hw_model == "Z690"
        assert info.serial_number == "BBSERIAL123"

    def test_from_response_empty_data(self) -> None:
        """Test from_response with empty/missing data."""
        from unraid_api.models import ServerInfo

        response: dict[str, object] = {}

        info = ServerInfo.from_response(response)

        assert info.uuid is None
        assert info.hostname is None
        assert info.manufacturer == "Lime Technology"
        assert info.model == "Unraid Unknown"
        assert info.sw_version == "Unknown"

    def test_from_response_partial_data(self) -> None:
        """Test from_response with partial data."""
        from unraid_api.models import ServerInfo

        response = {
            "info": {
                "system": {"uuid": "abc123"},
                "os": {"hostname": "MyServer"},
                "versions": {"core": {"unraid": "7.1.4"}},
            },
        }

        info = ServerInfo.from_response(response)

        assert info.uuid == "abc123"
        assert info.hostname == "MyServer"
        assert info.model == "Unraid 7.1.4"
        assert info.sw_version == "7.1.4"
        assert info.lan_ip is None
        assert info.license_type is None


class TestSystemMetrics:
    """Tests for SystemMetrics model."""

    def test_system_metrics_creation(self) -> None:
        """Test creating SystemMetrics with all fields."""
        from unraid_api.models import SystemMetrics

        metrics = SystemMetrics(
            cpu_percent=25.5,
            cpu_temperature=55.0,
            cpu_temperatures=[55.0, 52.0],
            cpu_power=65.5,
            memory_percent=50.0,
            memory_total=34359738368,
            memory_used=17179869184,
            memory_free=17179869184,
            memory_available=25769803776,
            swap_percent=10.0,
            swap_total=8589934592,
            swap_used=858993459,
            uptime=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        )

        assert metrics.cpu_percent == 25.5
        assert metrics.cpu_temperature == 55.0
        assert metrics.cpu_temperatures == [55.0, 52.0]
        assert metrics.cpu_power == 65.5
        assert metrics.memory_percent == 50.0
        assert metrics.memory_total == 34359738368
        assert metrics.memory_used == 17179869184
        assert metrics.memory_available == 25769803776
        assert metrics.swap_percent == 10.0
        assert metrics.uptime is not None

    def test_system_metrics_defaults(self) -> None:
        """Test SystemMetrics with default values."""
        from unraid_api.models import SystemMetrics

        metrics = SystemMetrics()

        assert metrics.cpu_percent is None
        assert metrics.cpu_temperature is None
        assert metrics.cpu_temperatures == []
        assert metrics.cpu_power is None
        assert metrics.memory_percent is None
        assert metrics.memory_total is None
        assert metrics.uptime is None

    def test_system_metrics_from_response(self) -> None:
        """Test from_response with full data."""
        from unraid_api.models import SystemMetrics

        response = {
            "metrics": {
                "cpu": {"percentTotal": 25.5},
                "memory": {
                    "total": 34359738368,
                    "used": 17179869184,
                    "free": 17179869184,
                    "available": 25769803776,
                    "percentTotal": 50.0,
                    "swapTotal": 8589934592,
                    "swapUsed": 858993459,
                    "percentSwapTotal": 10.0,
                },
            },
            "info": {
                "os": {"uptime": "2024-01-15T10:30:00Z"},
                "cpu": {"packages": {"temp": [55.0, 52.0], "totalPower": 65.5}},
            },
        }

        metrics = SystemMetrics.from_response(response)

        assert metrics.cpu_percent == 25.5
        assert metrics.cpu_temperature == 55.0
        assert metrics.cpu_temperatures == [55.0, 52.0]
        assert metrics.cpu_power == 65.5
        assert metrics.memory_percent == 50.0
        assert metrics.memory_total == 34359738368
        assert metrics.memory_used == 17179869184
        assert metrics.memory_available == 25769803776
        assert metrics.swap_percent == 10.0
        assert metrics.swap_total == 8589934592
        assert metrics.swap_used == 858993459
        assert metrics.uptime is not None

    def test_system_metrics_from_response_minimal(self) -> None:
        """Test from_response with minimal data."""
        from unraid_api.models import SystemMetrics

        response = {
            "metrics": {
                "cpu": {"percentTotal": 10.0},
                "memory": {"percentTotal": 30.0},
            },
        }

        metrics = SystemMetrics.from_response(response)

        assert metrics.cpu_percent == 10.0
        assert metrics.cpu_temperature is None
        assert metrics.cpu_temperatures == []
        assert metrics.cpu_power is None
        assert metrics.memory_percent == 30.0
        assert metrics.memory_total is None
        assert metrics.uptime is None

    def test_system_metrics_from_response_empty(self) -> None:
        """Test from_response with empty data."""
        from unraid_api.models import SystemMetrics

        response: dict[str, object] = {}

        metrics = SystemMetrics.from_response(response)

        assert metrics.cpu_percent is None
        assert metrics.cpu_temperature is None
        assert metrics.cpu_temperatures == []
        assert metrics.cpu_power is None
        assert metrics.memory_percent is None
        assert metrics.uptime is None

    def test_system_metrics_from_response_single_temp(self) -> None:
        """Test from_response with single CPU temperature."""
        from unraid_api.models import SystemMetrics

        response = {
            "metrics": {"cpu": {"percentTotal": 15.0}},
            "info": {"cpu": {"packages": {"temp": [45.0], "totalPower": 30.0}}},
        }

        metrics = SystemMetrics.from_response(response)

        assert metrics.cpu_temperature == 45.0
        assert metrics.cpu_temperatures == [45.0]
        assert metrics.cpu_power == 30.0

    def test_system_metrics_from_response_empty_temp_list(self) -> None:
        """Test from_response with empty temperature list."""
        from unraid_api.models import SystemMetrics

        response = {
            "info": {"cpu": {"packages": {"temp": [], "totalPower": None}}},
        }

        metrics = SystemMetrics.from_response(response)

        assert metrics.cpu_temperature is None
        assert metrics.cpu_temperatures == []
        assert metrics.cpu_power is None


class TestRegistrationModel:
    """Tests for Registration model."""

    def test_registration_with_all_fields(self) -> None:
        """Test Registration creation with all fields."""
        from unraid_api.models import Registration

        reg = Registration(
            id="registration:1",
            type="Pro",
            state="VALID",
            expiration="2025-12-31",
            updateExpiration="2025-12-31",
        )

        assert reg.id == "registration:1"
        assert reg.type == "Pro"
        assert reg.state == "VALID"
        assert reg.expiration == "2025-12-31"

    def test_registration_with_minimal_fields(self) -> None:
        """Test Registration creation with minimal fields."""
        from unraid_api.models import Registration

        reg = Registration()

        assert reg.id is None
        assert reg.type is None
        assert reg.state is None


class TestVarsModel:
    """Tests for Vars model (system configuration)."""

    def test_vars_basic_creation(self) -> None:
        """Test Vars model creation with basic fields."""
        from unraid_api.models import Vars

        vars_data = Vars(
            id="vars:1",
            version="7.2.3",
            name="MyServer",
            time_zone="America/New_York",
        )

        assert vars_data.id == "vars:1"
        assert vars_data.version == "7.2.3"
        assert vars_data.name == "MyServer"
        assert vars_data.time_zone == "America/New_York"

    def test_vars_from_graphql_response(self) -> None:
        """Test Vars creation from GraphQL response with aliases."""
        from unraid_api.models import Vars

        # Response uses camelCase from GraphQL
        data = {
            "id": "vars:1",
            "version": "7.2.3",
            "name": "Cube",
            "timeZone": "UTC",
            "workgroup": "WORKGROUP",
            "mdNumDisks": 4,
            "mdState": "STARTED",
            "fsState": "Running",
            "shareCount": 10,
            "shareSmbCount": 8,
        }

        vars_obj = Vars(**data)

        assert vars_obj.name == "Cube"
        assert vars_obj.time_zone == "UTC"
        assert vars_obj.workgroup == "WORKGROUP"
        assert vars_obj.md_num_disks == 4
        assert vars_obj.md_state == "STARTED"
        assert vars_obj.fs_state == "Running"
        assert vars_obj.share_count == 10
        assert vars_obj.share_smb_count == 8

    def test_vars_with_optional_fields(self) -> None:
        """Test Vars with optional fields as None."""
        from unraid_api.models import Vars

        vars_data = Vars(name="Server")

        assert vars_data.name == "Server"
        assert vars_data.version is None
        assert vars_data.md_num_disks is None
        assert vars_data.csrf_token is None

    def test_vars_all_field_categories(self) -> None:
        """Test Vars model with fields from all categories."""
        from unraid_api.models import Vars

        vars_data = Vars(
            # Basic info
            version="7.2.3",
            name="Unraid",
            time_zone="America/Chicago",
            comment="My Unraid Server",
            # Network
            use_ssl=True,
            port=80,
            portssl=443,
            use_ssh=True,
            port_ssh=22,
            # Array state
            md_state="STARTED",
            md_num_disks=8,
            fs_state="Running",
            # Shares
            share_smb_enabled=True,
            share_count=15,
        )

        assert vars_data.version == "7.2.3"
        assert vars_data.use_ssl is True
        assert vars_data.port == 80
        assert vars_data.md_num_disks == 8
        assert vars_data.share_count == 15


class TestServiceModel:
    """Tests for Service model."""

    def test_service_with_all_fields(self) -> None:
        """Test Service creation with all fields."""
        from unraid_api.models import Service, ServiceUptime

        service = Service(
            id="service:docker",
            name="docker",
            online=True,
            uptime=ServiceUptime(timestamp="2024-01-15T10:30:00Z"),
            version="24.0.7",
        )

        assert service.id == "service:docker"
        assert service.name == "docker"
        assert service.online is True
        assert service.uptime is not None
        assert service.uptime.timestamp == "2024-01-15T10:30:00Z"
        assert service.version == "24.0.7"


class TestFlashModel:
    """Tests for Flash model."""

    def test_flash_with_all_fields(self) -> None:
        """Test Flash creation with all fields."""
        from unraid_api.models import Flash

        flash = Flash(
            id="flash:1",
            product="Ultra Fit",
            vendor="SanDisk",
        )

        assert flash.id == "flash:1"
        assert flash.product == "Ultra Fit"
        assert flash.vendor == "SanDisk"


class TestOwnerModel:
    """Tests for Owner model."""

    def test_owner_with_all_fields(self) -> None:
        """Test Owner creation with all fields."""
        from unraid_api.models import Owner

        owner = Owner(
            username="admin",
            avatar="https://example.com/avatar.png",
            url="https://my.unraid.net",
        )

        assert owner.username == "admin"
        assert owner.avatar == "https://example.com/avatar.png"
        assert owner.url == "https://my.unraid.net"


class TestPluginModel:
    """Tests for Plugin model."""

    def test_plugin_with_all_fields(self) -> None:
        """Test Plugin creation with all fields."""
        from unraid_api.models import Plugin

        plugin = Plugin(
            name="Test Plugin",
            version="1.0.0",
            hasApiModule=True,
            hasCliModule=False,
        )

        assert plugin.name == "Test Plugin"
        assert plugin.version == "1.0.0"
        assert plugin.hasApiModule is True
        assert plugin.hasCliModule is False

    def test_plugin_with_minimal_fields(self) -> None:
        """Test Plugin creation with minimal fields."""
        from unraid_api.models import Plugin

        plugin = Plugin(name="Test", version="1.0")

        assert plugin.name == "Test"
        assert plugin.version == "1.0"
        assert plugin.hasApiModule is None
        assert plugin.hasCliModule is None


class TestDockerNetworkModel:
    """Tests for DockerNetwork model."""

    def test_docker_network_with_all_fields(self) -> None:
        """Test DockerNetwork creation with all fields."""
        from unraid_api.models import DockerNetwork

        network = DockerNetwork(
            id="network:bridge",
            name="bridge",
            created="2024-01-01T00:00:00Z",
            scope="local",
            driver="bridge",
            enableIPv6=False,
            internal=False,
            attachable=False,
            ingress=False,
            configOnly=False,
        )

        assert network.id == "network:bridge"
        assert network.name == "bridge"
        assert network.driver == "bridge"


class TestLogFileModels:
    """Tests for LogFile and LogFileContent models."""

    def test_log_file_creation(self) -> None:
        """Test LogFile creation."""
        from unraid_api.models import LogFile

        log = LogFile(
            name="syslog",
            path="/var/log/syslog",
            size=102400,
            modifiedAt="2024-01-15T10:30:00Z",
        )

        assert log.name == "syslog"
        assert log.path == "/var/log/syslog"
        assert log.size == 102400

    def test_log_file_content_creation(self) -> None:
        """Test LogFileContent creation."""
        from unraid_api.models import LogFileContent

        content = LogFileContent(
            path="/var/log/syslog",
            content="Log entry 1\nLog entry 2\n",
            totalLines=100,
            startLine=1,
        )

        assert content.path == "/var/log/syslog"
        assert content.content is not None
        assert "Log entry 1" in content.content
        assert content.totalLines == 100


class TestCloudModel:
    """Tests for Cloud model."""

    def test_cloud_with_all_fields(self) -> None:
        """Test Cloud creation with all fields."""
        from unraid_api.models import (
            ApiKeyResponse,
            Cloud,
            CloudResponse,
            MinigraphqlResponse,
            RelayResponse,
        )

        cloud = Cloud(
            error=None,
            apiKey=ApiKeyResponse(valid=True, error=None),
            relay=RelayResponse(status="connected", timeout="5000", error=None),
            minigraphql=MinigraphqlResponse(status="CONNECTED", timeout=30, error=None),
            cloud=CloudResponse(status="ok", ip="192.168.1.100", error=None),
            allowedOrigins=["http://localhost"],
        )

        assert cloud.cloud is not None
        assert cloud.cloud.status == "ok"
        assert cloud.apiKey is not None
        assert cloud.apiKey.valid is True
        assert len(cloud.allowedOrigins) == 1

    def test_cloud_with_error(self) -> None:
        """Test Cloud creation with error state."""
        from unraid_api.models import ApiKeyResponse, Cloud, CloudResponse

        cloud = Cloud(
            error="Connection failed",
            apiKey=ApiKeyResponse(valid=False, error="Invalid key"),
            cloud=CloudResponse(status="error", error="Connection failed"),
        )

        assert cloud.error == "Connection failed"
        assert cloud.cloud is not None
        assert cloud.cloud.status == "error"


class TestConnectModel:
    """Tests for Connect model."""

    def test_connect_signed_in(self) -> None:
        """Test Connect creation when signed in."""
        from unraid_api.models import Connect, DynamicRemoteAccessStatus

        connect = Connect(
            id="connect:1",
            dynamicRemoteAccess=DynamicRemoteAccessStatus(
                enabledType="UPNP",
                runningType="UPNP",
                error=None,
            ),
        )

        assert connect.id == "connect:1"
        assert connect.dynamicRemoteAccess is not None
        assert connect.dynamicRemoteAccess.enabledType == "UPNP"

    def test_connect_not_signed_in(self) -> None:
        """Test Connect creation when not signed in."""
        from unraid_api.models import Connect, DynamicRemoteAccessStatus

        connect = Connect(
            id="connect:1",
            dynamicRemoteAccess=DynamicRemoteAccessStatus(
                enabledType="DISABLED",
                runningType="DISABLED",
            ),
        )

        assert connect.dynamicRemoteAccess is not None
        assert connect.dynamicRemoteAccess.enabledType == "DISABLED"


class TestRemoteAccessModel:
    """Tests for RemoteAccess model."""

    def test_remote_access_enabled(self) -> None:
        """Test RemoteAccess creation when enabled."""
        from unraid_api.models import RemoteAccess

        remote = RemoteAccess(
            accessType="ALWAYS",
            forwardType="UPNP",
            port=443,
        )

        assert remote.accessType == "ALWAYS"
        assert remote.forwardType == "UPNP"
        assert remote.port == 443

    def test_remote_access_disabled(self) -> None:
        """Test RemoteAccess creation when disabled."""
        from unraid_api.models import RemoteAccess

        remote = RemoteAccess(accessType="DISABLED")

        assert remote.accessType == "DISABLED"
        assert remote.port is None


class TestDockerContainerExtendedFields:
    """Tests for extended DockerContainer fields."""

    def test_container_with_extended_fields(self) -> None:
        """Test DockerContainer with all extended fields."""
        from unraid_api.models import ContainerHostConfig, DockerContainer

        container = DockerContainer(
            id="abc123",
            name="test-container",
            names=["/test-container"],
            state="running",
            status="Up 5 days",
            image="nginx:latest",
            imageId="sha256:abc123",
            command="/docker-entrypoint.sh nginx",
            created=1704067200,
            sizeRootFs=150000000,
            labels={"com.docker.compose.project": "test"},
            networkSettings={"Networks": {"bridge": {}}},
            mounts=[{"Type": "bind", "Source": "/data", "Destination": "/data"}],
            hostConfig=ContainerHostConfig(networkMode="bridge"),
        )

        assert container.imageId == "sha256:abc123"
        assert container.command == "/docker-entrypoint.sh nginx"
        assert container.created == 1704067200
        assert container.sizeRootFs == 150000000
        assert container.labels is not None
        assert container.labels["com.docker.compose.project"] == "test"
        assert container.mounts is not None
        assert len(container.mounts) == 1
        assert container.hostConfig is not None
        assert container.hostConfig.networkMode == "bridge"

    def test_container_from_api_response_with_extended_fields(self) -> None:
        """Test DockerContainer.from_api_response with extended fields."""
        from unraid_api.models import DockerContainer

        data = {
            "id": "abc123",
            "names": ["/myapp"],
            "state": "running",
            "status": "Up 2 hours",
            "image": "myapp:latest",
            "imageId": "sha256:def456",
            "command": "python main.py",
            "created": 1704067200,
            "sizeRootFs": 200000000,
            "labels": {"maintainer": "test"},
            "networkSettings": {"IPAddress": "172.17.0.2"},
            "mounts": [],
            "hostConfig": {"networkMode": "host"},
            "ports": [],
        }

        container = DockerContainer.from_api_response(data)

        assert container.name == "myapp"
        assert container.imageId == "sha256:def456"
        assert container.command == "python main.py"
        assert container.created == 1704067200
        assert container.sizeRootFs == 200000000
        assert container.hostConfig is not None
        assert container.hostConfig.networkMode == "host"


class TestUPSExtendedFields:
    """Tests for UPS model extended fields."""

    def test_ups_battery_with_health(self) -> None:
        """Test UPSBattery with health field."""
        from unraid_api.models import UPSBattery

        battery = UPSBattery(
            chargeLevel=100,
            estimatedRuntime=1800,
            health="Good",
        )

        assert battery.chargeLevel == 100
        assert battery.estimatedRuntime == 1800
        assert battery.health == "Good"

    def test_ups_device_with_model(self) -> None:
        """Test UPSDevice with model field."""
        from unraid_api.models import UPSBattery, UPSDevice, UPSPower

        device = UPSDevice(
            id="ups:1",
            name="APC UPS",
            model="Back-UPS 1500",
            status="online",
            battery=UPSBattery(chargeLevel=95, estimatedRuntime=1200, health="Good"),
            power=UPSPower(
                inputVoltage=120.0, outputVoltage=120.0, loadPercentage=25.0
            ),
        )

        assert device.model == "Back-UPS 1500"
        assert device.battery.health == "Good"
