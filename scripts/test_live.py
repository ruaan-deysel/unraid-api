#!/usr/bin/env python3
"""Comprehensive live testing script for unraid-api - READ ONLY."""

import asyncio
import os
import sys

sys.path.insert(0, "src")

from unraid_api import UnraidClient


async def main() -> None:
    """Test all query methods against live server."""
    host = os.environ.get("UNRAID_HOST", "192.168.1.100")
    api_key = os.environ.get("UNRAID_API_KEY", "")

    if not api_key:
        print("ERROR: Set UNRAID_API_KEY environment variable")
        print("Usage: UNRAID_HOST=192.168.1.100 UNRAID_API_KEY=your-key python scripts/test_live.py")
        sys.exit(1)

    async with UnraidClient(
        host,
        api_key,
        verify_ssl=False,
    ) as client:
        tests = []
        print("=" * 60)
        print("COMPREHENSIVE LIVE API TEST - READ ONLY")
        print("=" * 60)

        # 1. Connection
        try:
            result = await client.test_connection()
            tests.append(("test_connection", "PASS"))
            print(f"✓ test_connection: {result}")
        except Exception as e:
            tests.append(("test_connection", f"FAIL: {e}"))
            print(f"✗ test_connection: {e}")

        # 2. Version
        try:
            result = await client.get_version()
            tests.append(("get_version", "PASS"))
            print(f"✓ get_version: Unraid {result.get('unraid')}, API {result.get('api')}")
        except Exception as e:
            tests.append(("get_version", f"FAIL: {e}"))
            print(f"✗ get_version: {e}")

        # 3. System Info
        try:
            result = await client.get_system_info()
            tests.append(("get_system_info", "PASS"))
            print(f"✓ get_system_info: {result.get('hostname')}")
        except Exception as e:
            tests.append(("get_system_info", f"FAIL: {e}"))
            print(f"✗ get_system_info: {e}")

        # 4. Registration
        try:
            result = await client.get_registration()
            tests.append(("get_registration", "PASS"))
            print(f"✓ get_registration: type={result.get('type')}")
        except Exception as e:
            tests.append(("get_registration", f"FAIL: {e}"))
            print(f"✗ get_registration: {e}")

        # 5. Vars
        try:
            result = await client.get_vars()
            tests.append(("get_vars", "PASS"))
            print(f"✓ get_vars: name={result.get('name')}, mdState={result.get('mdState')}")
        except Exception as e:
            tests.append(("get_vars", f"FAIL: {e}"))
            print(f"✗ get_vars: {e}")

        # 6. System Metrics (CPU temp & power)
        try:
            result = await client.get_system_metrics()
            tests.append(("get_system_metrics", "PASS"))
            print(f"✓ get_system_metrics: cpu={result.cpu_percent}%, temp={result.cpu_temperature}°C, power={result.cpu_power}W")
            print(f"  → cpu_temperatures: {result.cpu_temperatures}")
            print(f"  → memory: {result.memory_percent}%")
        except Exception as e:
            tests.append(("get_system_metrics", f"FAIL: {e}"))
            print(f"✗ get_system_metrics: {e}")

        # 7. Owner
        try:
            result = await client.get_owner()
            tests.append(("get_owner", "PASS"))
            print(f"✓ get_owner: {result.get('username')}")
        except Exception as e:
            tests.append(("get_owner", f"FAIL: {e}"))
            print(f"✗ get_owner: {e}")

        # 7. Flash
        try:
            result = await client.get_flash()
            tests.append(("get_flash", "PASS"))
            print(f"✓ get_flash: {result.get('vendor')} {result.get('product')}")
        except Exception as e:
            tests.append(("get_flash", f"FAIL: {e}"))
            print(f"✗ get_flash: {e}")

        # 8. Services
        try:
            result = await client.get_services()
            tests.append(("get_services", "PASS"))
            online = sum(1 for s in result if s.get("online"))
            print(f"✓ get_services: {len(result)} total, {online} online")
        except Exception as e:
            tests.append(("get_services", f"FAIL: {e}"))
            print(f"✗ get_services: {e}")

        # 9. Array
        try:
            result = await client.get_array_status()
            tests.append(("get_array_status", "PASS"))
            print(f"✓ get_array_status: state={result.get('state')}")
        except Exception as e:
            tests.append(("get_array_status", f"FAIL: {e}"))
            print(f"✗ get_array_status: {e}")

        # 10. Disks
        try:
            result = await client.get_disks()
            tests.append(("get_disks", "PASS"))
            print(f"✓ get_disks: {len(result)} disks")
        except Exception as e:
            tests.append(("get_disks", f"FAIL: {e}"))
            print(f"✗ get_disks: {e}")

        # 11. Shares
        try:
            result = await client.get_shares()
            tests.append(("get_shares", "PASS"))
            print(f"✓ get_shares: {len(result)} shares")
        except Exception as e:
            tests.append(("get_shares", f"FAIL: {e}"))
            print(f"✗ get_shares: {e}")

        # 12. Docker Containers
        try:
            result = await client.get_containers()
            tests.append(("get_containers", "PASS"))
            running = sum(1 for c in result if c.get("state") == "running")
            print(f"✓ get_containers: {len(result)} containers, {running} running")
        except Exception as e:
            tests.append(("get_containers", f"FAIL: {e}"))
            print(f"✗ get_containers: {e}")

        # 13. Docker Networks
        try:
            result = await client.get_docker_networks()
            tests.append(("get_docker_networks", "PASS"))
            print(f"✓ get_docker_networks: {len(result)} networks")
        except Exception as e:
            tests.append(("get_docker_networks", f"FAIL: {e}"))
            print(f"✗ get_docker_networks: {e}")

        # 14. VMs
        try:
            result = await client.get_vms()
            tests.append(("get_vms", "PASS"))
            print(f"✓ get_vms: {len(result)} VMs")
        except Exception as e:
            tests.append(("get_vms", f"FAIL: {e}"))
            print(f"✗ get_vms: {e}")

        # 15. UPS
        try:
            result = await client.get_ups_status()
            tests.append(("get_ups_status", "PASS"))
            print(f"✓ get_ups_status: {len(result)} devices")
        except Exception as e:
            tests.append(("get_ups_status", f"FAIL: {e}"))
            print(f"✗ get_ups_status: {e}")

        # 16. Plugins
        try:
            result = await client.get_plugins()
            tests.append(("get_plugins", "PASS"))
            print(f"✓ get_plugins: {len(result)} plugins")
        except Exception as e:
            tests.append(("get_plugins", f"FAIL: {e}"))
            print(f"✗ get_plugins: {e}")

        # 17. Notifications
        try:
            result = await client.get_notifications()
            tests.append(("get_notifications", "PASS"))
            print(f"✓ get_notifications: {len(result)} unread")
        except Exception as e:
            tests.append(("get_notifications", f"FAIL: {e}"))
            print(f"✗ get_notifications: {e}")

        # 18. Parity History
        try:
            result = await client.get_parity_history()
            tests.append(("get_parity_history", "PASS"))
            print(f"✓ get_parity_history: {len(result)} entries")
        except Exception as e:
            tests.append(("get_parity_history", f"FAIL: {e}"))
            print(f"✗ get_parity_history: {e}")

        # 19. Log Files
        try:
            result = await client.get_log_files()
            tests.append(("get_log_files", "PASS"))
            print(f"✓ get_log_files: {len(result)} files")
        except Exception as e:
            tests.append(("get_log_files", f"FAIL: {e}"))
            print(f"✗ get_log_files: {e}")

        # 20. Cloud
        try:
            result = await client.get_cloud()
            tests.append(("get_cloud", "PASS"))
            status = result.get("cloud", {}).get("status") if result.get("cloud") else "N/A"
            print(f"✓ get_cloud: status={status}")
        except Exception as e:
            tests.append(("get_cloud", f"FAIL: {e}"))
            print(f"✗ get_cloud: {e}")

        # 21. Connect
        try:
            result = await client.get_connect()
            tests.append(("get_connect", "PASS"))
            print(f"✓ get_connect: id={result.get('id')}")
        except Exception as e:
            tests.append(("get_connect", f"FAIL: {e}"))
            print(f"✗ get_connect: {e}")

        # 22. Remote Access
        try:
            result = await client.get_remote_access()
            tests.append(("get_remote_access", "PASS"))
            print(f"✓ get_remote_access: type={result.get('accessType')}")
        except Exception as e:
            tests.append(("get_remote_access", f"FAIL: {e}"))
            print(f"✗ get_remote_access: {e}")

        # Typed methods
        print("\n--- Typed Methods (Pydantic Models) ---")

        # 25. typed_get_vars
        try:
            result = await client.typed_get_vars()
            tests.append(("typed_get_vars", "PASS"))
            print(f"✓ typed_get_vars: name={result.name}")
        except Exception as e:
            tests.append(("typed_get_vars", f"FAIL: {e}"))
            print(f"✗ typed_get_vars: {e}")

        # 26. typed_get_registration
        try:
            result = await client.typed_get_registration()
            tests.append(("typed_get_registration", "PASS"))
            print(f"✓ typed_get_registration: type={result.type}")
        except Exception as e:
            tests.append(("typed_get_registration", f"FAIL: {e}"))
            print(f"✗ typed_get_registration: {e}")

        # 27. typed_get_services
        try:
            result = await client.typed_get_services()
            tests.append(("typed_get_services", "PASS"))
            print(f"✓ typed_get_services: {len(result)} services")
        except Exception as e:
            tests.append(("typed_get_services", f"FAIL: {e}"))
            print(f"✗ typed_get_services: {e}")

        # 28. typed_get_array
        try:
            result = await client.typed_get_array()
            tests.append(("typed_get_array", "PASS"))
            print(f"✓ typed_get_array: state={result.state}")
        except Exception as e:
            tests.append(("typed_get_array", f"FAIL: {e}"))
            print(f"✗ typed_get_array: {e}")

        # 29. typed_get_containers
        try:
            result = await client.typed_get_containers()
            tests.append(("typed_get_containers", "PASS"))
            print(f"✓ typed_get_containers: {len(result)} containers")
        except Exception as e:
            tests.append(("typed_get_containers", f"FAIL: {e}"))
            print(f"✗ typed_get_containers: {e}")

        # 30. typed_get_shares
        try:
            result = await client.typed_get_shares()
            tests.append(("typed_get_shares", "PASS"))
            print(f"✓ typed_get_shares: {len(result)} shares")
        except Exception as e:
            tests.append(("typed_get_shares", f"FAIL: {e}"))
            print(f"✗ typed_get_shares: {e}")

        # Summary
        print("\n" + "=" * 60)
        passed = sum(1 for _, r in tests if r == "PASS")
        print(f"RESULT: {passed}/{len(tests)} tests passed")
        if passed < len(tests):
            print("\nFailed:")
            for n, r in tests:
                if r != "PASS":
                    print(f"  {n}: {r}")


if __name__ == "__main__":
    asyncio.run(main())
