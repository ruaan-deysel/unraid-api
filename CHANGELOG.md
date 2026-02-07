# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.1] - 2026-02-07

### Added

- Refactored datetime parsing in Pydantic models using `BeforeValidator` with reusable `ParsedDatetime` annotated type
  - Consolidates repeated `field_validator` logic for cleaner, more maintainable code

### Fixed

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

[Unreleased]: https://github.com/ruaan-deysel/unraid-api/compare/v1.3.1...HEAD
[1.3.1]: https://github.com/ruaan-deysel/unraid-api/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/ruaan-deysel/unraid-api/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/ruaan-deysel/unraid-api/releases/tag/v1.2.2
