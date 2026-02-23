# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.6.0] - 2026-02-24

### Added

- **State constants module** (`unraid_api.const`) with all known API state values organized by domain (fixes #17)
  - `MIN_API_VERSION`, `MIN_UNRAID_VERSION` for version gating
  - Docker, VM, disk, parity, UPS, and array state constants
- **State helper properties** on models (fixes #17):
  - `DockerContainer.is_running` - True when container state is "running"
  - `VmDomain.is_running` - True when VM state is "running" or "idle"
  - `ArrayDisk.is_healthy` - True when disk status is "DISK_OK"
  - `ParityCheck.is_running` - True when status is "RUNNING" or "PAUSED"
  - `ParityCheck.has_problem` - True when status is "FAILED" or errors > 0
  - `UPSDevice.is_connected` - True when status is not "Offline" or "OFF"
- **`VersionInfo` model** returned by `get_version()` with typed `api` and `unraid` fields (fixes #21)
- **`ParityHistoryEntry` model** returned by `get_parity_history()` with typed fields and `duration_formatted` property (fixes #18)
  - Handles multiple date formats (ISO strings, epoch timestamps, datetime objects)
- **`check_compatibility()` method** on `UnraidClient` for version validation (fixes #20)
  - Raises `UnraidVersionError` if server version is below minimum requirements
  - Uses `packaging` library for robust semantic version comparison
- **`UnraidVersionError` exception** for incompatible server versions (fixes #20)
- **`format_bytes()` utility function** for human-readable byte formatting (fixes #15)
- **`SystemMetrics.average_cpu_temperature`** property - mean of all CPU package temps (fixes #15)
- **`SystemMetrics.memory_used` fallback** computation from `total - available` when API doesn't provide `used` (fixes #15)
- **UPS power calculation helper** `UPSDevice.calculate_power_watts(nominal_power)` (fixes #19)
- **`UPSBattery.runtime_formatted`** property for human-readable runtime display (fixes #19)
- Missing fields in `typed_get_containers()` GraphQL query: `imageId`, `isUpdateAvailable`, `webUiUrl`, `iconUrl` (fixes #12)
  - Extended fields (`isUpdateAvailable`, `webUiUrl`, `iconUrl`) are queried with automatic fallback for older API versions that don't support them (verified against official schema at `unraid/api`)
- `packaging` as a runtime dependency for version comparison

### Fixed

- **ZFS disk usage calculation** - `ArrayDisk.fs_used_bytes` and `usage_percent` now fall back to `fsSize - fsFree` when `fsUsed` is 0 or None, which is common on ZFS pools (fixes #16)
- **aiohttp exception wrapping** - all aiohttp exceptions are now properly mapped to the UnraidAPI exception hierarchy (fixes #22):
  - `ClientResponseError` (401/403) -> `UnraidAuthenticationError`
  - `ClientResponseError` (other) -> `UnraidAPIError`
  - `TimeoutError` during discovery -> `UnraidTimeoutError`
  - Session `close()` errors are now suppressed and logged
- Consumers no longer need to import `aiohttp` to handle errors

### Changed

- `get_version()` now returns `VersionInfo` model instead of `dict[str, str]`
- `get_parity_history()` now returns `list[ParityHistoryEntry]` instead of `list[dict]`

## [1.5.0] - 2026-02-07

### Added

- `restart_container(container_id, delay=1.0)` convenience method that encapsulates the stop/wait/start sequence
- Container log retrieval: `get_container_logs()` and `typed_get_container_logs()` with `tail` and `since` parameters
- User account query: `get_me()` and `typed_get_me()` for current authenticated user info
- API key management: `get_api_keys()`, `typed_get_api_keys()`, `create_api_key()`, `update_api_key()`, `delete_api_keys()`
- New Pydantic models: `UserAccount`, `ApiKey`, `Permission`, `DockerContainerLogs`, `DockerContainerLogLine`
- Refactored datetime parsing in Pydantic models using `BeforeValidator` with reusable `ParsedDatetime` annotated type
  - Consolidates repeated `field_validator` logic for cleaner, more maintainable code

### Fixed

- Silent fallback to default HTTPS port when HTTP probe fails on user-specified port (fixes #9)
  - When a non-default `http_port` is specified and the port is unreachable, `UnraidConnectionError` is now raised instead of silently connecting on port 443
  - Default port (80) behavior is unchanged — HTTPS fallback still works for standard HTTP→HTTPS upgrade
- Improved SSL/TLS detection with short-circuit logic when `http_port == https_port`
- Handle nginx 400 "plain HTTP to HTTPS port" error response to detect forced HTTPS configuration
- Comprehensive test coverage for SSL detection edge cases and session creation failures

## [1.4.0] - 2026-01-13

### Added
- New `UnraidSSLError` exception for SSL/TLS certificate verification failures
  - Raised when SSL certificate verification fails, hostname mismatches, or TLS handshake errors occur
  - Inherits from `UnraidConnectionError` for backwards compatibility
  - Enables cleaner error handling without string matching (fixes #4)
- Added `PLR0912` (too many branches) to ruff ignore list for complex error handling

### Changed
- SSL errors are now caught specifically and re-raised as `UnraidSSLError` instead of generic `UnraidConnectionError`

## [1.3.1] - 2026-01-11

### Added
- CPU temperature fields to `SystemMetrics` model:
  - `cpu_temperature` - First package temperature (most common use)
  - `cpu_temperatures` - All package temperatures (for multi-CPU systems)
  - `cpu_power` - Total CPU power consumption in watts
- Updated `get_system_metrics()` GraphQL query to fetch `info.cpu.packages`

### Fixed
- Issue #3: Add CPU temperature and power to SystemMetrics

## [1.3.0] - 2026-01-11

### Added

#### High-Level Typed Methods
All methods return Pydantic models for type-safe data access:

- `get_system_metrics()` - Returns `SystemMetrics` with CPU, memory, uptime
- `typed_get_array()` - Returns `UnraidArray` with state, capacity, disks
- `typed_get_containers()` - Returns `list[DockerContainer]`
- `typed_get_vms()` - Returns `list[VmDomain]`
- `typed_get_ups_devices()` - Returns `list[UPSDevice]`
- `typed_get_shares()` - Returns `list[Share]`
- `get_notification_overview()` - Returns `NotificationOverview`
- `typed_get_vars()` - Returns `Vars` (system configuration)
- `typed_get_registration()` - Returns `Registration` (license info)
- `typed_get_services()` - Returns `list[Service]`
- `typed_get_flash()` - Returns `Flash`
- `typed_get_owner()` - Returns `Owner`
- `typed_get_plugins()` - Returns `list[Plugin]`
- `typed_get_docker_networks()` - Returns `list[DockerNetwork]`
- `typed_get_log_files()` - Returns `list[LogFile]`
- `typed_get_cloud()` - Returns `Cloud`
- `typed_get_connect()` - Returns `Connect`
- `typed_get_remote_access()` - Returns `RemoteAccess`

#### Raw Data Methods
Return dict/list for flexible access:

- `get_array_status()` - Array state and capacity
- `get_disks()` / `get_physical_disks()` - Physical disk info
- `get_shares()` - User shares
- `get_containers()` - Docker containers
- `get_vms()` - Virtual machines
- `get_ups_status()` - UPS devices
- `get_notifications()` - Notifications list
- `get_parity_history()` - Parity check history
- `get_services()` - System services
- `get_vars()` - System variables
- `get_registration()` - Registration info
- `get_flash()` - Flash drive info
- `get_owner()` - Owner info
- `get_plugins()` - Installed plugins
- `get_docker_networks()` - Docker networks
- `get_log_files()` - Log file list
- `get_log_file(path)` - Log file contents
- `get_cloud()` - Cloud status
- `get_connect()` - Connect status
- `get_remote_access()` - Remote access config

#### New Pydantic Models
- `Vars` - System configuration (hostname, timezone, array state, etc.)
- `Registration` - License type, state, owner
- `Service` / `ServiceUptime` - System service status
- `Flash` - Flash drive vendor/product
- `Owner` - Server owner username
- `Plugin` - Plugin name, version, modules
- `DockerNetwork` - Network configuration
- `LogFile` / `LogFileContent` - Log file access
- `Cloud` / `CloudResponse` / `ApiKeyResponse` / `RelayResponse` / `MinigraphqlResponse` - Unraid Connect
- `Connect` / `DynamicRemoteAccessStatus` - Connect configuration
- `RemoteAccess` - Remote access settings
- `SystemMetrics` - CPU, memory, uptime metrics

#### Enhanced Existing Models
- `DockerContainer` - Added `sizeRootFs`, `labels`, `networkSettings`, `mounts`
- `UPSDevice` - Added `model` field
- `UPSBattery` - Added `health` field

### Changed

- `get_vars()` now returns a single `dict` (was incorrectly returning `list`)
- All typed methods follow `typed_get_*` naming convention
- Improved schema alignment with upstream Unraid API

### Fixed

- `Vars` type corrected from list to single object per GraphQL schema
- `Plugin` model aligned with actual API response (only name, version, hasApiModule, hasCliModule)
- `LogFile` model fixed (removed non-existent `id` field, added `size`, `modifiedAt`)
- `Cloud`, `Connect`, `RemoteAccess` models restructured to match actual API responses

## [1.2.2] - 2026-01-10

### Added
- Initial release with core functionality
- GraphQL query/mutation support
- Docker container control (start/stop/restart)
- VM management (start/stop/force-stop/pause/resume)
- Array operations (start/stop)
- Parity check control
- Disk spin up/down
- SSL auto-discovery
- Session injection for Home Assistant

### Models
- `ServerInfo`, `SystemInfo`
- `UnraidArray`, `ArrayDisk`, `ArrayCapacity`
- `DockerContainer`, `ContainerPort`, `ContainerHostConfig`
- `VmDomain`
- `UPSDevice`, `UPSBattery`, `UPSPower`
- `Share`
- `PhysicalDisk`
- `Notification`, `NotificationOverview`

[Unreleased]: https://github.com/ruaan-deysel/unraid-api/compare/v1.6.0...HEAD
[1.6.0]: https://github.com/ruaan-deysel/unraid-api/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/ruaan-deysel/unraid-api/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/ruaan-deysel/unraid-api/compare/v1.3.1...v1.4.0
[1.3.1]: https://github.com/ruaan-deysel/unraid-api/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/ruaan-deysel/unraid-api/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/ruaan-deysel/unraid-api/releases/tag/v1.2.2
