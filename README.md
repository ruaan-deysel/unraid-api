# Unraid GraphQL API Client

A comprehensive Python client and testing suite for the modern Unraid GraphQL API. This tool provides easy access to all aspects of your Unraid server including system information, array management, Docker containers, virtual machines, and more.

**Perfect for Home Assistant integrations and automation developers!**

## Features

- ✅ **Fully Updated for Latest Unraid API** - Compatible with Unraid 7.1.4+ and API 4.21.0+
- 🏠 **Home Assistant Ready** - Designed for building Home Assistant integrations
- 🐍 **Python Client** - Comprehensive programmatic interface
- 🔧 **cURL Testing Script** - Simple command-line testing
- 📊 **Complete Coverage** - Access all server data and operations
- 🔒 **Secure Authentication** - API key-based authentication
- 🚀 **Easy to Use** - Simple, intuitive interface

## Getting Started

### Prerequisites

- Python 3.7+
- Unraid server with GraphQL API enabled
- API key with appropriate permissions
- For shell script usage: bash, curl, and optionally jq for pretty-printing JSON

### Installation

1. Clone this repository:
```bash
git clone https://github.com/domalab/unraid-api-client.git
cd unraid-api-client
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

## Quick Start

### Python Client

The Python client (`unraid_api_client.py`) provides a comprehensive interface for the modern Unraid GraphQL API.

**Basic usage:**

```bash
# Query server information (CPU, memory, versions)
python3 unraid_api_client.py --ip YOUR_SERVER_IP --key YOUR_API_KEY --query info

# Query array status with all disks
python3 unraid_api_client.py --ip YOUR_SERVER_IP --key YOUR_API_KEY --query array

# Query Docker containers
python3 unraid_api_client.py --ip YOUR_SERVER_IP --key YOUR_API_KEY --query docker

# Run all available queries
python3 unraid_api_client.py --ip YOUR_SERVER_IP --key YOUR_API_KEY --query all
```

**Available query types:**

- `info`: Server information (CPU, memory, versions)
- `array`: Array status with all disk types (data, parity, cache)
- `docker`: Docker containers with detailed information
- `disks`: Physical disk information with SMART status
- `shares`: Network shares information
- `vms`: Virtual machines status
- `users`: Current user information
- `apikeys`: API keys management
- `notifications`: System notifications
- `all`: Execute all available queries

**Additional options:**

- `--direct`: Skip redirect detection and connect directly to the IP
- `--custom "query { ... }"`: Run a custom GraphQL query

**For Home Assistant developers:**

```python
from unraid_api_client import UnraidGraphQLClient

# Initialize client
client = UnraidGraphQLClient("192.168.1.100", "your_api_key")

# Get server info for sensors
server_info = client.get_server_info()
cpu_info = server_info['data']['info']['cpu']
memory_info = server_info['data']['info']['memory']

# Get array status for monitoring
array_status = client.get_array_status()
array_state = array_status['data']['array']['state']

# Get Docker containers for automation
containers = client.get_docker_containers()
container_list = containers['data']['docker']['containers']
```

## Advanced Features

### System Monitoring

Monitor system uptime and overall health:

```python
# Get system uptime and information
uptime_info = client.get_system_uptime()
print(f"Hostname: {uptime_info['hostname']}")
print(f"Uptime: {uptime_info['uptime']}")
print(f"OS: {uptime_info['distro']} {uptime_info['release']}")

# Get array usage summary
usage = client.get_array_usage_summary()
data_array = usage['data_array']
print(f"Data Array: {data_array['percent_used']}% used")
print(f"Cache: {usage['cache']['percent_used']}% used")

# Get disk health status
health = client.get_disk_health_status()
summary = health['summary']
print(f"Total Disks: {summary['total_disks']}")
print(f"Healthy Disks: {summary['healthy_disks']}")
print(f"Average Temperature: {summary['average_temperature']}°C")
print(f"Overall Health: {summary['overall_health']}")

# Get parity check status
parity = client.get_parity_check_status()
if parity['summary']['is_running']:
    print(f"Parity check running: {parity['summary']['progress']}%")
else:
    print(f"Last parity check: {parity['summary']['last_status']}")
```

### Disk Sleep State Monitoring

Monitor which disks are spinning or sleeping to optimize power consumption:

```python
# Get disk sleep status for all disks
sleep_status = client.get_disk_sleep_status()

print(f"Total disks: {sleep_status['summary']['total_disks']}")
print(f"Spinning: {sleep_status['summary']['spinning_count']}")
print(f"Sleeping: {sleep_status['summary']['sleeping_count']}")

# List sleeping disks
for disk in sleep_status['sleeping']:
    print(f"💤 {disk['name']} ({disk['device']}) - {disk['type']}")

# List spinning disks
for disk in sleep_status['spinning']:
    print(f"🔄 {disk['name']} ({disk['device']}) - {disk['type']}")
```

**Important Notes:**
- Querying disk information may wake up sleeping disks
- Use `include_array_disks=False` to only check unassigned disks
- Use `include_unassigned_disks=False` to only check array disks
- Disk queries may take 30+ seconds when disks are sleeping

### UPS Monitoring

Monitor UPS status, battery level, and power consumption:

```python
# Get UPS status summary (ideal for Home Assistant)
ups_status = client.get_ups_status_summary()

if ups_status['connected']:
    print(f"UPS Model: {ups_status['model']}")
    print(f"Status: {ups_status['status']}")
    print(f"Battery: {ups_status['battery_level']}%")
    print(f"Runtime: {ups_status['estimated_runtime']} minutes")
    print(f"Load: {ups_status['load_percentage']}%")
    print(f"On Battery: {ups_status['on_battery']}")
    print(f"Battery Low: {ups_status['battery_low']}")
else:
    print("No UPS connected")

# Get detailed UPS information
ups_devices = client.get_ups_devices()
ups_config = client.get_ups_configuration()
```

### Control Operations

Control Docker containers and virtual machines:

```python
# Docker container control
containers = client.get_docker_containers()
container_id = containers['data']['docker']['containers'][0]['id']

# Start/stop containers
client.start_docker_container(container_id)
client.stop_docker_container(container_id)

# VM control (if VMs are configured)
vms = client.get_vms()
if vms['data']['vms']['domains']:
    vm_id = vms['data']['vms']['domains'][0]['id']

    # VM lifecycle operations
    client.start_vm(vm_id)
    client.pause_vm(vm_id)
    client.resume_vm(vm_id)
    client.stop_vm(vm_id)  # Graceful shutdown
    client.stop_vm(vm_id, force=True)  # Force power off
    client.reboot_vm(vm_id)
```

**Control Operation Notes:**
- Always check current status before performing operations
- Use force stop only when necessary (may cause data loss)
- Container/VM IDs can be obtained from status queries

### API Limitations

**❌ Not Available:**
- Real-time CPU usage (requires GraphQL subscriptions)
- Real-time memory usage (requires GraphQL subscriptions)
- CPU/motherboard temperature sensors
- System fan speeds
- Detailed SMART disk attributes

**⚠️ Limited Availability:**
- Disk temperature: Array disks only (not unassigned disks)
- VM information: Basic status only (no detailed configuration)
- Disk queries may wake sleeping disks

**✅ Fully Available:**
- System uptime and OS information
- Array and disk usage statistics
- Disk health status and error counts
- UPS monitoring and power management
- Parity check status and history
- Docker container monitoring and control
- VM lifecycle management

### Shell Script Testing

The shell script (`test_api_curl.sh`) provides a simple testing interface using curl:

```bash
# Query server information
./test_api_curl.sh --type info

# Query Docker containers
./test_api_curl.sh --type docker

# Query notifications
./test_api_curl.sh --type notifications

# Query memory information
./test_api_curl.sh --type memory

# Query CPU information
./test_api_curl.sh --type cpu

# Query UPS devices
./test_api_curl.sh --type ups

# Query disk sleep status
./test_api_curl.sh --type disk-sleep

# Query verified system monitoring features
./test_api_curl.sh --type system-uptime
./test_api_curl.sh --type array-usage
./test_api_curl.sh --type disk-health
./test_api_curl.sh --type parity-status

# Use custom server and API key
./test_api_curl.sh --ip YOUR_SERVER_IP --key YOUR_API_KEY --type array
```

**Available shell script query types:**

**Basic Information:**
- `info`, `array`, `docker`, `disks`, `network`, `shares`, `vms`
- `notifications`, `users`, `apikeys`, `memory`, `cpu`

**Advanced Monitoring:**
- `ups`, `disk-sleep` (power management)
- `system-uptime`, `array-usage`, `disk-health`, `parity-status` (verified monitoring)

## Using the Unraid API

The Unraid API provides a GraphQL interface that allows you to interact with your Unraid server. This section will help you get started with exploring and using the API.

### Enabling the GraphQL Sandbox

1. First, enable developer mode using the CLI:

    ```bash
    unraid-api developer
    ```

2. Follow the prompts to enable the sandbox. This will allow you to access the Apollo Sandbox interface.

3. Access the GraphQL playground by navigating to:

    ```txt
    http://YOUR_SERVER_IP/graphql
    ```

### Authentication

Most queries and mutations require authentication. You can authenticate using either:

1. API Keys
2. Cookies (default method when signed into the WebGUI)

#### Creating an API Key

Use the CLI to create an API key:

```bash
unraid-api apikey --create
```

Follow the prompts to set:

- Name
- Description
- Roles
- Permissions

The generated API key should be included in your GraphQL requests as a header:

```json
{
    "x-api-key": "YOUR_API_KEY"
}
```

## GraphQL Schema

The Unraid GraphQL API provides access to various aspects of your Unraid server:

### Available Schemas

- Server information (CPU, memory, OS)
- Array status and disk management
- Docker containers and networks
- Network interfaces and shares
- Virtual machines
- User accounts
- Notifications
- API key management
- And more...

### Schema Types

The API includes several core types:

#### Base Types

- `Node`: Interface for objects with unique IDs - please see [Object Identification](https://graphql.org/learn/global-object-identification/)
- `JSON`: For complex JSON data
- `DateTime`: For timestamp values
- `Long`: For 64-bit integers

#### Resource Types

- `Array`: Array and disk management
- `Docker`: Container and network management
- `Info`: System information
- `Config`: Server configuration
- `Connect`: Remote access settings

### Role-Based Access

Available roles:

- `admin`: Full access
- `connect`: Remote access features
- `guest`: Limited read access

## GraphQL Query Examples

Here are example GraphQL queries for the modern Unraid API:

### System Information

```graphql
query {
    info {
        cpu {
            id
            manufacturer
            brand
            cores
            threads
            clockSpeed
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
            core {
                unraid
                api
                kernel
            }
            packages {
                openssl
                node
                npm
            }
        }
    }
}
```

### Array Status

```graphql
query {
    array {
        state
        capacity {
            kilobytes {
                free
                used
                total
            }
            disks {
                free
                used
                total
            }
        }
        boot {
            name
            device
            size
            temp
            type
        }
        parities {
            name
            device
            size
            status
            type
        }
        disks {
            name
            device
            size
            status
            type
            temp
            fsSize
            fsFree
            fsUsed
        }
        caches {
            name
            device
            size
            temp
            status
            type
        }
    }
}
```

### Docker Containers

```graphql
query {
    docker {
        containers {
            id
            names
            image
            state
            status
            autoStart
            ports {
                ip
                privatePort
                publicPort
                type
            }
        }
    }
}
```

### Disk Information

```graphql
query {
    disks {
        id
        device
        name
        type
        size
        vendor
        firmwareRevision
        serialNum
        interfaceType
        smartStatus
        temperature
        isSpinning
        partitions {
            name
            fsType
            size
        }
    }
}
```

### Notifications

```graphql
query {
    notifications {
        list(filter: { type: UNREAD, offset: 0, limit: 10 }) {
            id
            title
            subject
            description
            importance
            link
            type
            timestamp
            formattedTimestamp
        }
        overview {
            unread {
                info
                warning
                alert
                total
            }
        }
    }
}
```

### Mutation Examples

The API also supports mutations for controlling your Unraid server:

#### Array Control

```graphql
# Start the array
mutation {
    array {
        setState(input: { desiredState: START }) {
            state
        }
    }
}

# Stop the array
mutation {
    array {
        setState(input: { desiredState: STOP }) {
            state
        }
    }
}
```

#### Docker Container Control

```graphql
# Start a container
mutation {
    docker {
        start(id: "container_id") {
            id
            state
            status
        }
    }
}

# Stop a container
mutation {
    docker {
        stop(id: "container_id") {
            id
            state
            status
        }
    }
}
```

#### Virtual Machine Control

```graphql
# Start a VM
mutation {
    vm {
        start(id: "vm_id") {
            uuid
            name
            state
        }
    }
}

# Stop a VM
mutation {
    vm {
        stop(id: "vm_id") {
            uuid
            name
            state
        }
    }
}
```

#### Parity Check Control

```graphql
# Start a parity check
mutation {
    parityCheck {
        start(correct: false) {
            status
            progress
        }
    }
}

# Pause a parity check
mutation {
    parityCheck {
        pause {
            status
            progress
        }
    }
}
```

## Home Assistant Integration

This client is specifically designed to work well with Home Assistant. Here are examples for different monitoring scenarios:

### Basic Array Status Sensor

```python
import asyncio
from homeassistant.helpers.entity import Entity
from unraid_api_client import UnraidGraphQLClient

class UnraidArraySensor(Entity):
    def __init__(self, server_ip, api_key):
        self.client = UnraidGraphQLClient(server_ip, api_key)
        self._state = None

    @property
    def state(self):
        return self._state

    async def async_update(self):
        # Get array status
        result = await asyncio.get_event_loop().run_in_executor(
            None, self.client.get_array_status
        )
        if 'data' in result:
            self._state = result['data']['array']['state']
```

### UPS Monitoring Sensor

```python
class UnraidUPSSensor(Entity):
    def __init__(self, server_ip, api_key):
        self.client = UnraidGraphQLClient(server_ip, api_key)
        self._attributes = {}

    @property
    def state(self):
        return self._attributes.get('battery_level', 'unknown')

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_update(self):
        result = await asyncio.get_event_loop().run_in_executor(
            None, self.client.get_ups_status_summary
        )
        if result.get('connected'):
            self._attributes = {
                'battery_level': result.get('battery_level'),
                'status': result.get('status'),
                'runtime': result.get('estimated_runtime'),
                'load': result.get('load_percentage'),
                'on_battery': result.get('on_battery'),
                'battery_low': result.get('battery_low')
            }
```

### System Monitoring Sensor

```python
class UnraidSystemSensor(Entity):
    def __init__(self, server_ip, api_key):
        self.client = UnraidGraphQLClient(server_ip, api_key)
        self._attributes = {}

    @property
    def state(self):
        return self._attributes.get('array_percent_used', 0)

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_update(self):
        # Get comprehensive system status
        uptime = await asyncio.get_event_loop().run_in_executor(
            None, self.client.get_system_uptime
        )
        usage = await asyncio.get_event_loop().run_in_executor(
            None, self.client.get_array_usage_summary
        )
        health = await asyncio.get_event_loop().run_in_executor(
            None, self.client.get_disk_health_status
        )

        self._attributes = {
            'hostname': uptime.get('hostname'),
            'uptime': uptime.get('uptime'),
            'os_version': uptime.get('release'),
            'array_state': usage.get('array_state'),
            'array_percent_used': usage['data_array']['percent_used'],
            'cache_percent_used': usage['cache']['percent_used'],
            'total_disks': health['summary']['total_disks'],
            'healthy_disks': health['summary']['healthy_disks'],
            'average_temperature': health['summary']['average_temperature'],
            'overall_health': health['summary']['overall_health']
        }
```

### Disk Sleep Monitoring Sensor

```python
class UnraidDiskSleepSensor(Entity):
    def __init__(self, server_ip, api_key):
        self.client = UnraidGraphQLClient(server_ip, api_key)
        self._attributes = {}

    @property
    def state(self):
        return self._attributes.get('sleeping_count', 0)

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_update(self):
        # Only check array disks to avoid waking unassigned disks
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.client.get_disk_sleep_status(
                include_array_disks=True,
                include_unassigned_disks=False
            )
        )
        self._attributes = {
            'total_disks': result['summary']['total_disks'],
            'spinning_count': result['summary']['spinning_count'],
            'sleeping_count': result['summary']['sleeping_count'],
            'spinning_disks': [d['name'] for d in result['spinning']],
            'sleeping_disks': [d['name'] for d in result['sleeping']]
        }
```

## Best Practices

1. **Start Small**: Begin with basic queries and gradually add more fields
2. **Error Handling**: Always check for errors in the response
3. **Rate Limiting**: Respect API rate limits in your applications
4. **Security**: Keep API keys secure and use appropriate permissions
5. **Testing**: Use the cURL script to test queries before implementing

## Troubleshooting

### Common Issues

1. **Connection Errors**: Ensure your Unraid server has the GraphQL API enabled
2. **Authentication Errors**: Verify your API key has the correct permissions
3. **Schema Errors**: Use the GraphQL introspection to verify field names
4. **Timeout Errors**: Some queries (like detailed disk info) may take longer

### Getting Help

- Check the GraphQL schema using introspection queries
- Use the Apollo Sandbox if available on your server
- Review the error messages for specific field or permission issues

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## License

This project is open-source software provided as-is for the Unraid community.
