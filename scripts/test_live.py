#!/usr/bin/env python3
"""Comprehensive live testing script for unraid-api - READ ONLY."""

import asyncio
import os
import sys

sys.path.insert(0, "src")

from unraid_api import UnraidClient
from unraid_api.models import ParityCheck, format_bytes


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

        # 2. Version (Issue #21 - now returns VersionInfo model)
        try:
            result = await client.get_version()
            if not hasattr(result, "api") or not hasattr(result, "unraid"):
                raise TypeError(f"Expected VersionInfo model, got {type(result).__name__}")
            tests.append(("get_version", "PASS"))
            print(f"✓ get_version: Unraid {result.unraid}, API {result.api} (type={type(result).__name__})")
        except Exception as e:
            tests.append(("get_version", f"FAIL: {e}"))
            print(f"✗ get_version: {e}")

        # 3. Compatibility Check (Issue #20)
        try:
            await client.check_compatibility()
            tests.append(("check_compatibility", "PASS"))
            print("✓ check_compatibility: server is compatible")
        except Exception as e:
            tests.append(("check_compatibility", f"FAIL: {e}"))
            print(f"✗ check_compatibility: {e}")

        # 4. System Info
        try:
            result = await client.get_system_info()
            tests.append(("get_system_info", "PASS"))
            print(f"✓ get_system_info: {result.get('hostname')}")
        except Exception as e:
            tests.append(("get_system_info", f"FAIL: {e}"))
            print(f"✗ get_system_info: {e}")

        # 5. Registration
        try:
            result = await client.get_registration()
            tests.append(("get_registration", "PASS"))
            print(f"✓ get_registration: type={result.get('type')}")
        except Exception as e:
            tests.append(("get_registration", f"FAIL: {e}"))
            print(f"✗ get_registration: {e}")

        # 6. Vars
        try:
            result = await client.get_vars()
            tests.append(("get_vars", "PASS"))
            print(f"✓ get_vars: name={result.get('name')}, mdState={result.get('mdState')}")
        except Exception as e:
            tests.append(("get_vars", f"FAIL: {e}"))
            print(f"✗ get_vars: {e}")

        # 7. System Metrics (Issue #15 - average_cpu_temperature, memory_used fallback, format_bytes)
        try:
            result = await client.get_system_metrics()
            avg_temp = result.average_cpu_temperature
            mem_used = result.memory_used
            mem_fmt = format_bytes(result.memory_used)
            tests.append(("get_system_metrics", "PASS"))
            print(f"✓ get_system_metrics: cpu={result.cpu_percent}%, temp={result.cpu_temperature}°C, power={result.cpu_power}W")
            print(f"  → cpu_temperatures: {result.cpu_temperatures}")
            print(f"  → avg_cpu_temperature: {avg_temp}")
            print(f"  → memory: {result.memory_percent}%, used={mem_fmt}, total={format_bytes(result.memory_total)}")
        except Exception as e:
            tests.append(("get_system_metrics", f"FAIL: {e}"))
            print(f"✗ get_system_metrics: {e}")

        # 8. Owner
        try:
            result = await client.get_owner()
            tests.append(("get_owner", "PASS"))
            print(f"✓ get_owner: {result.get('username')}")
        except Exception as e:
            tests.append(("get_owner", f"FAIL: {e}"))
            print(f"✗ get_owner: {e}")

        # 9. Flash
        try:
            result = await client.get_flash()
            tests.append(("get_flash", "PASS"))
            print(f"✓ get_flash: {result.get('vendor')} {result.get('product')}")
        except Exception as e:
            tests.append(("get_flash", f"FAIL: {e}"))
            print(f"✗ get_flash: {e}")

        # 10. Services
        try:
            result = await client.get_services()
            tests.append(("get_services", "PASS"))
            online = sum(1 for s in result if s.get("online"))
            print(f"✓ get_services: {len(result)} total, {online} online")
        except Exception as e:
            tests.append(("get_services", f"FAIL: {e}"))
            print(f"✗ get_services: {e}")

        # 11. Array
        try:
            result = await client.get_array_status()
            tests.append(("get_array_status", "PASS"))
            print(f"✓ get_array_status: state={result.get('state')}")
        except Exception as e:
            tests.append(("get_array_status", f"FAIL: {e}"))
            print(f"✗ get_array_status: {e}")

        # 12. Array Disks (safe - doesn't wake sleeping disks)
        try:
            result = await client.get_array_disks()
            total_disks = len(result.get("disks", []))
            parities = len(result.get("parities", []))
            caches = len(result.get("caches", []))
            all_disks = result.get("disks", []) + result.get("parities", []) + result.get("caches", [])
            spinning = sum(1 for d in all_disks if d.get("isSpinning"))
            standby = len(all_disks) - spinning
            tests.append(("get_array_disks", "PASS"))
            print(f"✓ get_array_disks: {total_disks} data, {parities} parity, {caches} cache ({spinning} spinning, {standby} standby)")
        except Exception as e:
            tests.append(("get_array_disks", f"FAIL: {e}"))
            print(f"✗ get_array_disks: {e}")

        # 13. Shares
        try:
            result = await client.get_shares()
            tests.append(("get_shares", "PASS"))
            print(f"✓ get_shares: {len(result)} shares")
        except Exception as e:
            tests.append(("get_shares", f"FAIL: {e}"))
            print(f"✗ get_shares: {e}")

        # 14. Docker Containers
        try:
            result = await client.get_containers()
            tests.append(("get_containers", "PASS"))
            running = sum(1 for c in result if c.get("state") == "running")
            print(f"✓ get_containers: {len(result)} containers, {running} running")
        except Exception as e:
            tests.append(("get_containers", f"FAIL: {e}"))
            print(f"✗ get_containers: {e}")

        # 15. Docker Networks
        try:
            result = await client.get_docker_networks()
            tests.append(("get_docker_networks", "PASS"))
            print(f"✓ get_docker_networks: {len(result)} networks")
        except Exception as e:
            tests.append(("get_docker_networks", f"FAIL: {e}"))
            print(f"✗ get_docker_networks: {e}")

        # 16. VMs
        try:
            result = await client.get_vms()
            tests.append(("get_vms", "PASS"))
            print(f"✓ get_vms: {len(result)} VMs")
        except Exception as e:
            tests.append(("get_vms", f"FAIL: {e}"))
            print(f"✗ get_vms: {e}")

        # 17. UPS
        try:
            result = await client.get_ups_status()
            tests.append(("get_ups_status", "PASS"))
            print(f"✓ get_ups_status: {len(result)} devices")
        except Exception as e:
            tests.append(("get_ups_status", f"FAIL: {e}"))
            print(f"✗ get_ups_status: {e}")

        # 18. Plugins
        try:
            result = await client.get_plugins()
            tests.append(("get_plugins", "PASS"))
            print(f"✓ get_plugins: {len(result)} plugins")
        except Exception as e:
            tests.append(("get_plugins", f"FAIL: {e}"))
            print(f"✗ get_plugins: {e}")

        # 19. Notifications
        try:
            result = await client.get_notifications()
            tests.append(("get_notifications", "PASS"))
            print(f"✓ get_notifications: {len(result)} unread")
        except Exception as e:
            tests.append(("get_notifications", f"FAIL: {e}"))
            print(f"✗ get_notifications: {e}")

        # 20. Parity History (Issue #18 - now returns list[ParityHistoryEntry])
        try:
            result = await client.get_parity_history()
            tests.append(("get_parity_history", "PASS"))
            print(f"✓ get_parity_history: {len(result)} entries (type={type(result[0]).__name__ if result else 'N/A'})")
            for entry in result[:2]:
                print(f"  → date={entry.date}, duration={entry.duration_formatted}, errors={entry.errors}")
        except Exception as e:
            tests.append(("get_parity_history", f"FAIL: {e}"))
            print(f"✗ get_parity_history: {e}")

        # 21. Log Files
        try:
            result = await client.get_log_files()
            tests.append(("get_log_files", "PASS"))
            print(f"✓ get_log_files: {len(result)} files")
        except Exception as e:
            tests.append(("get_log_files", f"FAIL: {e}"))
            print(f"✗ get_log_files: {e}")

        # 22. Cloud
        try:
            result = await client.get_cloud()
            tests.append(("get_cloud", "PASS"))
            status = result.get("cloud", {}).get("status") if result.get("cloud") else "N/A"
            print(f"✓ get_cloud: status={status}")
        except Exception as e:
            tests.append(("get_cloud", f"FAIL: {e}"))
            print(f"✗ get_cloud: {e}")

        # 23. Connect
        try:
            result = await client.get_connect()
            tests.append(("get_connect", "PASS"))
            print(f"✓ get_connect: id={result.get('id')}")
        except Exception as e:
            tests.append(("get_connect", f"FAIL: {e}"))
            print(f"✗ get_connect: {e}")

        # 24. Remote Access
        try:
            result = await client.get_remote_access()
            tests.append(("get_remote_access", "PASS"))
            print(f"✓ get_remote_access: type={result.get('accessType')}")
        except Exception as e:
            tests.append(("get_remote_access", f"FAIL: {e}"))
            print(f"✗ get_remote_access: {e}")

        # 25. User Account
        try:
            result = await client.typed_get_me()
            tests.append(("typed_get_me", "PASS"))
            print(f"✓ typed_get_me: name={result.name}, roles={result.roles}")
        except Exception as e:
            tests.append(("typed_get_me", f"FAIL: {e}"))
            print(f"✗ typed_get_me: {e}")

        # 26. API Keys
        try:
            result = await client.typed_get_api_keys()
            tests.append(("typed_get_api_keys", "PASS"))
            print(f"✓ typed_get_api_keys: {len(result)} keys")
        except Exception as e:
            tests.append(("typed_get_api_keys", f"FAIL: {e}"))
            print(f"✗ typed_get_api_keys: {e}")

        # --- Typed Methods (Pydantic Models) ---
        print("\n--- Typed Methods (Pydantic Models) ---")

        # 27. typed_get_vars
        try:
            result = await client.typed_get_vars()
            tests.append(("typed_get_vars", "PASS"))
            print(f"✓ typed_get_vars: name={result.name}")
        except Exception as e:
            tests.append(("typed_get_vars", f"FAIL: {e}"))
            print(f"✗ typed_get_vars: {e}")

        # 28. typed_get_registration
        try:
            result = await client.typed_get_registration()
            tests.append(("typed_get_registration", "PASS"))
            print(f"✓ typed_get_registration: type={result.type}")
        except Exception as e:
            tests.append(("typed_get_registration", f"FAIL: {e}"))
            print(f"✗ typed_get_registration: {e}")

        # 29. typed_get_services
        try:
            result = await client.typed_get_services()
            tests.append(("typed_get_services", "PASS"))
            print(f"✓ typed_get_services: {len(result)} services")
        except Exception as e:
            tests.append(("typed_get_services", f"FAIL: {e}"))
            print(f"✗ typed_get_services: {e}")

        # 30. typed_get_array (Issues #16, #17 - ZFS fallback, is_healthy)
        try:
            result = await client.typed_get_array()
            tests.append(("typed_get_array", "PASS"))
            print(f"✓ typed_get_array: state={result.state}, disks={len(result.disks)}")
            for disk in result.disks[:3]:
                print(f"  → {disk.name or disk.id}: healthy={disk.is_healthy}, used={format_bytes(disk.fs_used_bytes)}, {disk.usage_percent}%")
        except Exception as e:
            tests.append(("typed_get_array", f"FAIL: {e}"))
            print(f"✗ typed_get_array: {e}")

        # 31. typed_get_containers (Issue #12 - new fields, Issue #17 - is_running)
        try:
            result = await client.typed_get_containers()
            tests.append(("typed_get_containers", "PASS"))
            print(f"✓ typed_get_containers: {len(result)} containers")
            for c in result[:3]:
                update = " [UPDATE]" if getattr(c, "isUpdateAvailable", False) else ""
                print(f"  → {c.names}: running={c.is_running}, icon={getattr(c, 'iconUrl', None)}{update}")
        except Exception as e:
            tests.append(("typed_get_containers", f"FAIL: {e}"))
            print(f"✗ typed_get_containers: {e}")

        # 32. typed_get_vms (Issue #17 - is_running)
        try:
            result = await client.typed_get_vms()
            tests.append(("typed_get_vms", "PASS"))
            print(f"✓ typed_get_vms: {len(result)} VMs")
            for vm in result[:3]:
                print(f"  → {vm.name}: running={vm.is_running}, state={vm.state}")
        except Exception as e:
            tests.append(("typed_get_vms", f"FAIL: {e}"))
            print(f"✗ typed_get_vms: {e}")

        # 33. typed_get_ups_devices (Issue #19 - is_connected, calculate_power_watts, runtime_formatted)
        try:
            result = await client.typed_get_ups_devices()
            tests.append(("typed_get_ups_devices", "PASS"))
            print(f"✓ typed_get_ups_devices: {len(result)} devices")
            for ups in result:
                print(f"  → {ups.name}: connected={ups.is_connected}, status={ups.status}")
                if ups.battery:
                    print(f"    battery: charge={ups.battery.chargeLevel}%, runtime={ups.battery.runtime_formatted}")
                watts = ups.calculate_power_watts(1500)
                if watts is not None:
                    print(f"    est. power: {watts:.0f}W (1500W nominal)")
        except Exception as e:
            tests.append(("typed_get_ups_devices", f"FAIL: {e}"))
            print(f"✗ typed_get_ups_devices: {e}")

        # 34. typed_get_shares
        try:
            result = await client.typed_get_shares()
            tests.append(("typed_get_shares", "PASS"))
            print(f"✓ typed_get_shares: {len(result)} shares")
        except Exception as e:
            tests.append(("typed_get_shares", f"FAIL: {e}"))
            print(f"✗ typed_get_shares: {e}")

        # 35. typed_get_flash
        try:
            result = await client.typed_get_flash()
            tests.append(("typed_get_flash", "PASS"))
            print(f"✓ typed_get_flash: {result.vendor} {result.product}")
        except Exception as e:
            tests.append(("typed_get_flash", f"FAIL: {e}"))
            print(f"✗ typed_get_flash: {e}")

        # 36. typed_get_owner
        try:
            result = await client.typed_get_owner()
            tests.append(("typed_get_owner", "PASS"))
            print(f"✓ typed_get_owner: {result.username}")
        except Exception as e:
            tests.append(("typed_get_owner", f"FAIL: {e}"))
            print(f"✗ typed_get_owner: {e}")

        # 37. typed_get_plugins
        try:
            result = await client.typed_get_plugins()
            tests.append(("typed_get_plugins", "PASS"))
            print(f"✓ typed_get_plugins: {len(result)} plugins")
        except Exception as e:
            tests.append(("typed_get_plugins", f"FAIL: {e}"))
            print(f"✗ typed_get_plugins: {e}")

        # 38. typed_get_docker_networks
        try:
            result = await client.typed_get_docker_networks()
            tests.append(("typed_get_docker_networks", "PASS"))
            print(f"✓ typed_get_docker_networks: {len(result)} networks")
        except Exception as e:
            tests.append(("typed_get_docker_networks", f"FAIL: {e}"))
            print(f"✗ typed_get_docker_networks: {e}")

        # 39. typed_get_log_files
        try:
            result = await client.typed_get_log_files()
            tests.append(("typed_get_log_files", "PASS"))
            print(f"✓ typed_get_log_files: {len(result)} files")
        except Exception as e:
            tests.append(("typed_get_log_files", f"FAIL: {e}"))
            print(f"✗ typed_get_log_files: {e}")

        # 40. get_notification_overview
        try:
            result = await client.get_notification_overview()
            tests.append(("get_notification_overview", "PASS"))
            print(f"✓ get_notification_overview: unread={result.unread.total}, archive={result.archive.total}")
        except Exception as e:
            tests.append(("get_notification_overview", f"FAIL: {e}"))
            print(f"✗ get_notification_overview: {e}")

        # 41. typed_get_cloud
        try:
            result = await client.typed_get_cloud()
            tests.append(("typed_get_cloud", "PASS"))
            print(f"✓ typed_get_cloud: type={type(result).__name__}")
        except Exception as e:
            tests.append(("typed_get_cloud", f"FAIL: {e}"))
            print(f"✗ typed_get_cloud: {e}")

        # 42. typed_get_connect
        try:
            result = await client.typed_get_connect()
            tests.append(("typed_get_connect", "PASS"))
            print(f"✓ typed_get_connect: type={type(result).__name__}")
        except Exception as e:
            tests.append(("typed_get_connect", f"FAIL: {e}"))
            print(f"✗ typed_get_connect: {e}")

        # 43. typed_get_remote_access
        try:
            result = await client.typed_get_remote_access()
            tests.append(("typed_get_remote_access", "PASS"))
            print(f"✓ typed_get_remote_access: type={type(result).__name__}")
        except Exception as e:
            tests.append(("typed_get_remote_access", f"FAIL: {e}"))
            print(f"✗ typed_get_remote_access: {e}")

        # 44. Parity check helpers (Issue #17)
        try:
            array_raw = await client.get_array_status()
            parity_data = array_raw.get("parityCheck")
            if parity_data:
                parity = ParityCheck(**parity_data)
                tests.append(("parity_check_helpers", "PASS"))
                print(f"✓ parity_check_helpers: running={parity.is_running}, has_problem={parity.has_problem}")
            else:
                tests.append(("parity_check_helpers", "PASS (no data)"))
                print("✓ parity_check_helpers: no parity check data (normal)")
        except Exception as e:
            tests.append(("parity_check_helpers", f"FAIL: {e}"))
            print(f"✗ parity_check_helpers: {e}")

        # Summary
        print("\n" + "=" * 60)
        passed = sum(1 for _, r in tests if r.startswith("PASS"))
        print(f"RESULT: {passed}/{len(tests)} tests passed")
        if passed < len(tests):
            print("\nFailed:")
            for n, r in tests:
                if not r.startswith("PASS"):
                    print(f"  {n}: {r}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
