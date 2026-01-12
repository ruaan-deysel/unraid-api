# unraid-api

[![CI](https://github.com/ruaan-deysel/unraid-api/actions/workflows/ci.yml/badge.svg)](https://github.com/ruaan-deysel/unraid-api/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/unraid-api.svg)](https://badge.fury.io/py/unraid-api)
[![Python versions](https://img.shields.io/pypi/pyversions/unraid-api.svg)](https://pypi.org/project/unraid-api/)
[![Coverage](https://codecov.io/gh/ruaan-deysel/unraid-api/branch/main/graph/badge.svg)](https://codecov.io/gh/ruaan-deysel/unraid-api)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An async Python client library for the Unraid GraphQL API (v4.21.0+, Unraid 7.1.4+).

## Features

- 🔄 **Async/await** - Built with `aiohttp` for non-blocking operations
- 🏠 **Home Assistant ready** - Accepts external `aiohttp.ClientSession` for integration
- 🔒 **Secure by design** - GraphQL variables, no string interpolation
- 📦 **Typed** - Full type hints with `py.typed` marker (PEP 561)
- 🧩 **Pydantic models** - Structured response parsing
- 🔌 **SSL auto-discovery** - Handles Unraid's "No", "Yes", and "Strict" SSL modes
- ⚡ **Redirect handling** - Supports myunraid.net remote access

## Installation

```bash
pip install unraid-api
```

## Quick Start

```python
import asyncio
from unraid_api import UnraidClient

async def main():
    async with UnraidClient("192.168.1.100", "your-api-key") as client:
        # Test connection
        if await client.test_connection():
            print("Connected!")

            # Get version info
            version = await client.get_version()
            print(f"Unraid {version['unraid']}, API {version['api']}")

asyncio.run(main())
```

## Usage Examples

### Basic Queries

```python
async with UnraidClient(host, api_key) as client:
    # Custom GraphQL query
    result = await client.query("""
        query {
            info {
                os { hostname uptime }
                cpu { name cores threads }
                memory { total used }
            }
        }
    """)
    print(result["info"]["os"]["hostname"])
```

### Docker Container Control

```python
async with UnraidClient(host, api_key) as client:
    # Start a container
    await client.start_container("container:plex")

    # Stop a container
    await client.stop_container("container:plex")
```

### VM Management

```python
async with UnraidClient(host, api_key) as client:
    # Start a VM
    await client.start_vm("vm:windows-11")

    # Stop a VM
    await client.stop_vm("vm:windows-11")
```

### Array Operations

```python
async with UnraidClient(host, api_key) as client:
    # Start/stop array
    await client.start_array()
    await client.stop_array()

    # Parity check
    await client.start_parity_check(correct=True)
    await client.pause_parity_check()
    await client.resume_parity_check()
    await client.cancel_parity_check()

    # Disk spin control
    await client.spin_up_disk("disk:1")
    await client.spin_down_disk("disk:1")
```

### Session Injection (Home Assistant)

```python
import aiohttp
from unraid_api import UnraidClient

async def setup_client(session: aiohttp.ClientSession):
    """Use shared session from Home Assistant."""
    client = UnraidClient(
        host="192.168.1.100",
        api_key="your-api-key",
        session=session,  # Injected session won't be closed by client
        verify_ssl=False,
    )
    return client
```

## Pydantic Models

Response data can be parsed into typed models:

```python
from unraid_api.models import DockerContainer, VmDomain, UnraidArray

# Parse container data
container = DockerContainer(**container_data)
print(f"{container.name}: {container.state}")

# Parse array data
array = UnraidArray(**array_data)
print(f"Array: {array.state}, Capacity: {array.capacity.usage_percent}%")
```

## Exception Handling

```python
from unraid_api import UnraidClient
from unraid_api.exceptions import (
    UnraidAPIError,
    UnraidAuthenticationError,
    UnraidConnectionError,
    UnraidSSLError,
    UnraidTimeoutError,
)

async with UnraidClient(host, api_key) as client:
    try:
        await client.query("query { online }")
    except UnraidAuthenticationError:
        print("Invalid API key")
    except UnraidSSLError:
        print("SSL certificate verification failed")
    except UnraidConnectionError:
        print("Cannot reach server")
    except UnraidTimeoutError:
        print("Request timed out")
    except UnraidAPIError as e:
        print(f"API error: {e}")
```

## API Reference

### UnraidClient

#### Core Methods

| Method | Description |
|--------|-------------|
| `test_connection()` | Test if server is reachable |
| `get_version()` | Get Unraid and API version |
| `get_server_info()` | Get server info for device registration |
| `query(query, variables)` | Execute GraphQL query |
| `mutate(mutation, variables)` | Execute GraphQL mutation |

#### High-Level Typed Methods (Pydantic Models)

| Method | Returns | Description |
|--------|---------|-------------|
| `get_system_metrics()` | `SystemMetrics` | CPU, memory, temperature, power, uptime |
| `typed_get_array()` | `UnraidArray` | Array state, capacity, disks |
| `typed_get_containers()` | `list[DockerContainer]` | All Docker containers |
| `typed_get_vms()` | `list[VmDomain]` | All virtual machines |
| `typed_get_ups_devices()` | `list[UPSDevice]` | UPS devices with battery info |
| `typed_get_shares()` | `list[Share]` | User shares with usage |
| `get_notification_overview()` | `NotificationOverview` | Notification counts |
| `typed_get_vars()` | `Vars` | System configuration variables |
| `typed_get_registration()` | `Registration` | License information |
| `typed_get_services()` | `list[Service]` | System services status |
| `typed_get_flash()` | `Flash` | Flash drive info |
| `typed_get_owner()` | `Owner` | Owner information |
| `typed_get_plugins()` | `list[Plugin]` | Installed API plugins |
| `typed_get_docker_networks()` | `list[DockerNetwork]` | Docker networks |
| `typed_get_log_files()` | `list[LogFile]` | Available log files |
| `typed_get_cloud()` | `Cloud` | Unraid Connect cloud status |
| `typed_get_connect()` | `Connect` | Connect configuration |
| `typed_get_remote_access()` | `RemoteAccess` | Remote access settings |

#### Raw Data Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_array_status()` | `dict` | Array state and capacity |
| `get_disks()` | `list[dict]` | Physical disks |
| `get_shares()` | `list[dict]` | User shares |
| `get_containers()` | `list[dict]` | Docker containers |
| `get_vms()` | `list[dict]` | Virtual machines |
| `get_ups_status()` | `list[dict]` | UPS devices |
| `get_notifications()` | `list[dict]` | Notifications |
| `get_parity_history()` | `list[dict]` | Parity check history |
| `get_services()` | `list[dict]` | System services |
| `get_plugins()` | `list[dict]` | Installed plugins |
| `get_docker_networks()` | `list[dict]` | Docker networks |
| `get_log_files()` | `list[dict]` | Log files |
| `get_log_file(path)` | `dict` | Log file contents |

#### Control Methods

| Method | Description |
|--------|-------------|
| `start_container(id)` | Start Docker container |
| `stop_container(id)` | Stop Docker container |
| `restart_container(id)` | Restart Docker container |
| `start_vm(id)` | Start VM |
| `stop_vm(id)` | Stop VM (graceful) |
| `force_stop_vm(id)` | Force stop VM |
| `pause_vm(id)` | Pause VM |
| `resume_vm(id)` | Resume paused VM |
| `start_array()` | Start disk array |
| `stop_array()` | Stop disk array |
| `start_parity_check(correct)` | Start parity check |
| `pause_parity_check()` | Pause parity check |
| `resume_parity_check()` | Resume parity check |
| `cancel_parity_check()` | Cancel parity check |
| `spin_up_disk(id)` | Spin up disk |
| `spin_down_disk(id)` | Spin down disk |

### Models

#### System Models
- `ServerInfo` - Server info for HA device registration
- `SystemInfo` - System information
- `SystemMetrics` - CPU, memory, temperature, power, uptime metrics
- `Vars` - System configuration variables
- `Registration` - License/registration info
- `Flash` - Flash drive information
- `Owner` - Server owner info

#### Storage Models
- `UnraidArray` - Array state and disks
- `ArrayDisk` - Individual array disk
- `ArrayCapacity` - Capacity calculations
- `PhysicalDisk` - Physical disk details
- `Share` - User share with usage

#### Docker/VM Models
- `DockerContainer` - Container with ports, state, mounts
- `DockerNetwork` - Docker network configuration
- `VmDomain` - Virtual machine details

#### Service Models
- `Service` - System service status
- `UPSDevice` - UPS with battery/power info
- `Plugin` - Installed plugin info
- `LogFile` - Log file metadata
- `LogFileContent` - Log file contents

#### Network Models
- `Cloud` - Unraid Connect cloud status
- `Connect` - Connect configuration
- `RemoteAccess` - Remote access settings

#### Notification Models
- `Notification` - System notification
- `NotificationOverview` - Notification counts

### Exceptions

| Exception | Parent | Description |
|-----------|--------|-------------|
| `UnraidAPIError` | `Exception` | Base exception for all API errors |
| `UnraidConnectionError` | `UnraidAPIError` | Connection failures |
| `UnraidSSLError` | `UnraidConnectionError` | SSL certificate verification failures |
| `UnraidAuthenticationError` | `UnraidAPIError` | Authentication failures (invalid API key) |
| `UnraidTimeoutError` | `UnraidAPIError` | Request timeout |

**Note:** `UnraidSSLError` inherits from `UnraidConnectionError`, so it can be caught with either exception type for backwards compatibility.

## Requirements

- Python 3.11+
- Unraid 7.1.4+ with API 4.21.0+
- API key with appropriate permissions

## Development

```bash
# Clone repository
git clone https://github.com/ruaan-deysel/unraid-api.git
cd unraid-api

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v --cov=src/unraid_api

# Lint and type check
ruff check .
ruff format .
mypy src/
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please ensure:
1. Tests are written first (TDD)
2. All tests pass with 80%+ coverage
3. No linting errors (`ruff check . && mypy src/`)
4. GraphQL variables used (no string interpolation)

## Links

- [Official Unraid API Repository](https://github.com/unraid/api)
- [GraphQL API Reference](UNRAIDAPI.md)
- [PyPI Package](https://pypi.org/project/unraid-api/)
