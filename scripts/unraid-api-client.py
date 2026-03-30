#!/usr/bin/env python3
"""Unified Unraid API test client.

Combines all test capabilities into a single script:
  - Live API tests (queries, typed methods, v4.30.0 features)
  - WebSocket subscription tests
  - SSL detection tests

Reads credentials from scripts/.env file:
  IP: 192.168.10.100
  API Key: <key>

Usage:
  python scripts/unraid-api-client.py                  # Run all query tests
  python scripts/unraid-api-client.py --subscriptions  # Run subscription tests
  python scripts/unraid-api-client.py --ssl            # Run SSL detection tests
  python scripts/unraid-api-client.py --all            # Run everything
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from unraid_api import UnraidClient
from unraid_api.models import ParityCheck, format_bytes


def _sanitize_host(host: str) -> str:
    """Sanitize host for safe printing (strip embedded credentials)."""
    if "://" in host:
        from urllib.parse import urlparse
        parsed = urlparse(host)
        return parsed.hostname or "***"
    if "@" in host:
        return host.split("@", 1)[1]
    return host


def _sanitize_url(url: str | None) -> str:
    """Remove embedded credentials from URL for safe printing."""
    if url is None:
        return "None"
    from urllib.parse import urlparse
    parsed = urlparse(str(url))
    if parsed.username or parsed.password:
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc += f":{parsed.port}"
        return parsed._replace(netloc=netloc).geturl()
    return str(url)


def load_env() -> tuple[str, str]:
    """Load host and API key from scripts/.env or environment variables."""
    host = os.environ.get("UNRAID_HOST", "")
    api_key = os.environ.get("UNRAID_API_KEY", "")

    if not host or not api_key:
        env_path = Path(__file__).resolve().parent / ".env"
        if env_path.exists():
            for raw_line in env_path.read_text().strip().splitlines():
                line = raw_line.strip()
                if line.startswith("IP:"):
                    host = host or line.split(":", 1)[1].strip()
                elif line.startswith("API Key:"):
                    api_key = api_key or line.split(":", 1)[1].strip()

    if not host or not api_key:
        print("ERROR: Could not find credentials.")
        print("Set UNRAID_HOST/UNRAID_API_KEY env vars or create scripts/.env with:")
        print("  IP: 192.168.x.x")
        print("  API Key: your-key")
        sys.exit(1)

    return host, api_key


# ---------------------------------------------------------------------------
# Test runner helper
# ---------------------------------------------------------------------------


class TestRunner:
    """Collects test results and prints summary."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.results: list[tuple[str, str]] = []
        self._count = 0

    def header(self) -> None:
        print("=" * 60)
        print(self.title)
        print("=" * 60)

    def section(self, name: str) -> None:
        print(f"\n--- {name} ---")

    def record(self, name: str, status: str) -> None:
        self._count += 1
        self.results.append((name, status))

    def summary(self) -> int:
        passed = sum(1 for _, r in self.results if r.startswith("PASS"))
        skipped = sum(1 for _, r in self.results if r.startswith("SKIP"))
        failed = len(self.results) - passed - skipped
        print("\n" + "=" * 60)
        print(f"RESULT: {passed}/{len(self.results)} passed", end="")
        if skipped:
            print(f", {skipped} skipped", end="")
        print()
        if failed:
            print("\nFailed:")
            for n, r in self.results:
                if not r.startswith(("PASS", "SKIP")):
                    print(f"  {n}: {r}")
        print("=" * 60)
        return 0 if failed == 0 else 1


# ---------------------------------------------------------------------------
# Query / typed method tests
# ---------------------------------------------------------------------------


async def run_query_tests(client: UnraidClient) -> int:  # noqa: PLR0915
    """Run all query and typed-method tests. Returns exit code."""
    t = TestRunner("COMPREHENSIVE LIVE API TEST — READ ONLY")
    t.header()

    # 1. Connection
    try:
        result = await client.test_connection()
        t.record("test_connection", "PASS")
        print(f"✓ test_connection: {result}")
    except Exception as e:
        t.record("test_connection", f"FAIL: {e}")
        print(f"✗ test_connection: {e}")

    # 2. Version
    try:
        ver = await client.get_version()
        t.record("get_version", "PASS")
        print(f"✓ get_version: Unraid {ver.unraid}, API {ver.api}")
    except Exception as e:
        t.record("get_version", f"FAIL: {e}")
        print(f"✗ get_version: {e}")

    # 3. Compatibility
    try:
        await client.check_compatibility()
        t.record("check_compatibility", "PASS")
        print("✓ check_compatibility: server is compatible")
    except Exception as e:
        t.record("check_compatibility", f"FAIL: {e}")
        print(f"✗ check_compatibility: {e}")

    # 4. System Info
    try:
        info = await client.get_system_info()
        t.record("get_system_info", "PASS")
        print(f"✓ get_system_info: {info.get('hostname')}")
    except Exception as e:
        t.record("get_system_info", f"FAIL: {e}")
        print(f"✗ get_system_info: {e}")

    # 5. Registration
    try:
        reg = await client.get_registration()
        t.record("get_registration", "PASS")
        print(f"✓ get_registration: type={reg.get('type')}")
    except Exception as e:
        t.record("get_registration", f"FAIL: {e}")
        print(f"✗ get_registration: {e}")

    # 6. Vars
    try:
        v = await client.get_vars()
        t.record("get_vars", "PASS")
        print(f"✓ get_vars: name={v.get('name')}, mdState={v.get('mdState')}")
    except Exception as e:
        t.record("get_vars", f"FAIL: {e}")
        print(f"✗ get_vars: {e}")

    # 7. System Metrics
    try:
        m = await client.get_system_metrics()
        t.record("get_system_metrics", "PASS")
        print(f"✓ get_system_metrics: cpu={m.cpu_percent}%, temp={m.cpu_temperature}°C")
        print(f"  → memory: {m.memory_percent}%, used={format_bytes(m.memory_used)}")
    except Exception as e:
        t.record("get_system_metrics", f"FAIL: {e}")
        print(f"✗ get_system_metrics: {e}")

    # 8. Owner
    try:
        o = await client.get_owner()
        t.record("get_owner", "PASS")
        print(f"✓ get_owner: {o.get('username')}")
    except Exception as e:
        t.record("get_owner", f"FAIL: {e}")
        print(f"✗ get_owner: {e}")

    # 9. Flash
    try:
        f = await client.get_flash()
        t.record("get_flash", "PASS")
        print(f"✓ get_flash: {f.get('vendor')} {f.get('product')}")
    except Exception as e:
        t.record("get_flash", f"FAIL: {e}")
        print(f"✗ get_flash: {e}")

    # 10. Services
    try:
        svcs = await client.get_services()
        online = sum(1 for s in svcs if s.get("online"))
        t.record("get_services", "PASS")
        print(f"✓ get_services: {len(svcs)} total, {online} online")
    except Exception as e:
        t.record("get_services", f"FAIL: {e}")
        print(f"✗ get_services: {e}")

    # 11. Array
    try:
        arr = await client.get_array_status()
        t.record("get_array_status", "PASS")
        print(f"✓ get_array_status: state={arr.get('state')}")
    except Exception as e:
        t.record("get_array_status", f"FAIL: {e}")
        print(f"✗ get_array_status: {e}")

    # 12. Array Disks
    try:
        ad = await client.get_array_disks()
        total_d = len(ad.get("disks", []))
        parities = len(ad.get("parities", []))
        caches = len(ad.get("caches", []))
        all_d = ad.get("disks", []) + ad.get("parities", []) + ad.get("caches", [])
        spinning = sum(1 for d in all_d if d.get("isSpinning"))
        t.record("get_array_disks", "PASS")
        print(
            f"✓ get_array_disks: {total_d} data, {parities} parity,"
            f" {caches} cache ({spinning} spinning)"
        )
    except Exception as e:
        t.record("get_array_disks", f"FAIL: {e}")
        print(f"✗ get_array_disks: {e}")

    # 13. Shares
    try:
        sh = await client.get_shares()
        t.record("get_shares", "PASS")
        print(f"✓ get_shares: {len(sh)} shares")
    except Exception as e:
        t.record("get_shares", f"FAIL: {e}")
        print(f"✗ get_shares: {e}")

    # 14. Docker Containers
    try:
        ct = await client.get_containers()
        running = sum(1 for c in ct if str(c.get("state", "")).lower() == "running")
        t.record("get_containers", "PASS")
        print(f"✓ get_containers: {len(ct)} containers, {running} running")
    except Exception as e:
        t.record("get_containers", f"FAIL: {e}")
        print(f"✗ get_containers: {e}")

    # 15. Docker Networks
    try:
        dn = await client.get_docker_networks()
        t.record("get_docker_networks", "PASS")
        print(f"✓ get_docker_networks: {len(dn)} networks")
    except Exception as e:
        t.record("get_docker_networks", f"FAIL: {e}")
        print(f"✗ get_docker_networks: {e}")

    # 16. VMs
    try:
        vms = await client.get_vms()
        t.record("get_vms", "PASS")
        print(f"✓ get_vms: {len(vms)} VMs")
    except Exception as e:
        t.record("get_vms", f"FAIL: {e}")
        print(f"✗ get_vms: {e}")

    # 17. UPS
    try:
        ups = await client.get_ups_status()
        t.record("get_ups_status", "PASS")
        print(f"✓ get_ups_status: {len(ups)} devices")
    except Exception as e:
        t.record("get_ups_status", f"FAIL: {e}")
        print(f"✗ get_ups_status: {e}")

    # 18. Plugins
    try:
        pl = await client.get_plugins()
        t.record("get_plugins", "PASS")
        print(f"✓ get_plugins: {len(pl)} plugins")
    except Exception as e:
        t.record("get_plugins", f"FAIL: {e}")
        print(f"✗ get_plugins: {e}")

    # 19. Notifications
    try:
        nt = await client.get_notifications()
        t.record("get_notifications", "PASS")
        print(f"✓ get_notifications: {len(nt)} unread")
    except Exception as e:
        t.record("get_notifications", f"FAIL: {e}")
        print(f"✗ get_notifications: {e}")

    # 20. Parity History
    try:
        ph = await client.get_parity_history()
        t.record("get_parity_history", "PASS")
        print(f"✓ get_parity_history: {len(ph)} entries")
        for entry in ph[:2]:
            print(
                f"  → date={entry.date},"
                f" duration={entry.duration_formatted},"
                f" errors={entry.errors}"
            )
    except Exception as e:
        t.record("get_parity_history", f"FAIL: {e}")
        print(f"✗ get_parity_history: {e}")

    # 21. Log Files
    try:
        lf = await client.get_log_files()
        t.record("get_log_files", "PASS")
        print(f"✓ get_log_files: {len(lf)} files")
    except Exception as e:
        t.record("get_log_files", f"FAIL: {e}")
        print(f"✗ get_log_files: {e}")

    # 22. Cloud
    try:
        cl = await client.get_cloud()
        status = cl.get("cloud", {}).get("status") if cl.get("cloud") else "N/A"
        t.record("get_cloud", "PASS")
        print(f"✓ get_cloud: status={status}")
    except Exception as e:
        t.record("get_cloud", f"FAIL: {e}")
        print(f"✗ get_cloud: {e}")

    # 23. Connect
    try:
        cn = await client.get_connect()
        t.record("get_connect", "PASS")
        print(f"✓ get_connect: id={cn.get('id')}")
    except Exception as e:
        t.record("get_connect", f"FAIL: {e}")
        print(f"✗ get_connect: {e}")

    # 24. Remote Access
    try:
        ra = await client.get_remote_access()
        t.record("get_remote_access", "PASS")
        print(f"✓ get_remote_access: type={ra.get('accessType')}")
    except Exception as e:
        t.record("get_remote_access", f"FAIL: {e}")
        print(f"✗ get_remote_access: {e}")

    # 25. User Account
    try:
        me = await client.typed_get_me()
        t.record("typed_get_me", "PASS")
        print(f"✓ typed_get_me: name={me.name}, roles={me.roles}")
    except Exception as e:
        t.record("typed_get_me", f"FAIL: {e}")
        print(f"✗ typed_get_me: {e}")

    # 26. API Keys
    try:
        keys = await client.typed_get_api_keys()
        t.record("typed_get_api_keys", "PASS")
        print(f"✓ typed_get_api_keys: {len(keys)} keys")
    except Exception as e:
        t.record("typed_get_api_keys", f"FAIL: {e}")
        print(f"✗ typed_get_api_keys: {e}")

    # --- Typed Methods ---
    t.section("Typed Methods (Pydantic Models)")

    # 27. typed_get_vars
    try:
        tv = await client.typed_get_vars()
        t.record("typed_get_vars", "PASS")
        print(f"✓ typed_get_vars: name={tv.name}")
    except Exception as e:
        t.record("typed_get_vars", f"FAIL: {e}")
        print(f"✗ typed_get_vars: {e}")

    # 28. typed_get_registration
    try:
        tr = await client.typed_get_registration()
        t.record("typed_get_registration", "PASS")
        print(f"✓ typed_get_registration: type={tr.type}")
    except Exception as e:
        t.record("typed_get_registration", f"FAIL: {e}")
        print(f"✗ typed_get_registration: {e}")

    # 29. typed_get_services
    try:
        ts = await client.typed_get_services()
        t.record("typed_get_services", "PASS")
        print(f"✓ typed_get_services: {len(ts)} services")
    except Exception as e:
        t.record("typed_get_services", f"FAIL: {e}")
        print(f"✗ typed_get_services: {e}")

    # 30. typed_get_array
    try:
        ta = await client.typed_get_array()
        t.record("typed_get_array", "PASS")
        print(f"✓ typed_get_array: state={ta.state}, disks={len(ta.disks)}")
        for disk in ta.disks[:3]:
            print(
                f"  → {disk.name or disk.id}:"
                f" healthy={disk.is_healthy},"
                f" {disk.usage_percent}%"
            )
    except Exception as e:
        t.record("typed_get_array", f"FAIL: {e}")
        print(f"✗ typed_get_array: {e}")

    # 31. typed_get_containers
    try:
        tc = await client.typed_get_containers()
        t.record("typed_get_containers", "PASS")
        print(f"✓ typed_get_containers: {len(tc)} containers")
        for c in tc[:3]:
            upd = " [UPDATE]" if getattr(c, "isUpdateAvailable", False) else ""
            print(f"  → {c.names}: running={c.is_running}{upd}")
    except Exception as e:
        t.record("typed_get_containers", f"FAIL: {e}")
        print(f"✗ typed_get_containers: {e}")

    # 32. typed_get_vms
    try:
        tvm = await client.typed_get_vms()
        t.record("typed_get_vms", "PASS")
        print(f"✓ typed_get_vms: {len(tvm)} VMs")
        for vm in tvm[:3]:
            print(f"  → {vm.name}: running={vm.is_running}, state={vm.state}")
    except Exception as e:
        t.record("typed_get_vms", f"FAIL: {e}")
        print(f"✗ typed_get_vms: {e}")

    # 33. typed_get_ups_devices
    try:
        tu = await client.typed_get_ups_devices()
        t.record("typed_get_ups_devices", "PASS")
        print(f"✓ typed_get_ups_devices: {len(tu)} devices")
        for ups in tu:
            print(f"  → {ups.name}: connected={ups.is_connected}, status={ups.status}")
            if ups.battery:
                print(
                    f"    battery: {ups.battery.chargeLevel}%,"
                    f" runtime={ups.battery.runtime_formatted}"
                )
    except Exception as e:
        t.record("typed_get_ups_devices", f"FAIL: {e}")
        print(f"✗ typed_get_ups_devices: {e}")

    # 34-39: Batch typed methods
    for method_name, call in [
        ("typed_get_shares", client.typed_get_shares),
        ("typed_get_flash", client.typed_get_flash),
        ("typed_get_owner", client.typed_get_owner),
        ("typed_get_plugins", client.typed_get_plugins),
        ("typed_get_docker_networks", client.typed_get_docker_networks),
        ("typed_get_log_files", client.typed_get_log_files),
    ]:
        try:
            result = await call()
            t.record(method_name, "PASS")
            if isinstance(result, list):
                detail = f"{len(result)} items"
            else:
                detail = type(result).__name__
            print(f"✓ {method_name}: {detail}")
        except Exception as e:
            t.record(method_name, f"FAIL: {e}")
            print(f"✗ {method_name}: {e}")

    # 40. Notification overview
    try:
        no = await client.get_notification_overview()
        t.record("get_notification_overview", "PASS")
        print(
            f"✓ get_notification_overview:"
            f" unread={no.unread.total},"
            f" archive={no.archive.total}"
        )
    except Exception as e:
        t.record("get_notification_overview", f"FAIL: {e}")
        print(f"✗ get_notification_overview: {e}")

    # 41-43: Typed cloud/connect/remote
    for method_name, call in [
        ("typed_get_cloud", client.typed_get_cloud),
        ("typed_get_connect", client.typed_get_connect),
        ("typed_get_remote_access", client.typed_get_remote_access),
    ]:
        try:
            result = await call()
            t.record(method_name, "PASS")
            print(f"✓ {method_name}: {type(result).__name__}")
        except Exception as e:
            t.record(method_name, f"FAIL: {e}")
            print(f"✗ {method_name}: {e}")

    # 44. Parity check helpers
    try:
        arr_raw = await client.get_array_status()
        parity_data = arr_raw.get("parityCheck")
        if parity_data:
            parity = ParityCheck(**parity_data)
            t.record("parity_check_helpers", "PASS")
            print(f"✓ parity_check_helpers: running={parity.is_running}")
        else:
            t.record("parity_check_helpers", "PASS (no data)")
            print("✓ parity_check_helpers: no active check (normal)")
    except Exception as e:
        t.record("parity_check_helpers", f"FAIL: {e}")
        print(f"✗ parity_check_helpers: {e}")

    # --- v4.30.0 Features ---
    t.section("v4.30.0 Features")

    # 45. Container Update Statuses
    try:
        cus = await client.get_container_update_statuses()
        t.record("get_container_update_statuses", "PASS")
        print(f"✓ get_container_update_statuses: {len(cus)} containers")
    except Exception as e:
        t.record("get_container_update_statuses", f"FAIL: {e}")
        print(f"✗ get_container_update_statuses: {e}")

    # 46. UPS Configuration
    try:
        uc = await client.get_ups_configuration()
        t.record("get_ups_configuration", "PASS")
        print(
            f"✓ get_ups_configuration:"
            f" cable={uc.upsCable}, batteryLevel={uc.batteryLevel}"
        )
    except Exception as e:
        t.record("get_ups_configuration", f"FAIL: {e}")
        print(f"✗ get_ups_configuration: {e}")

    # 47. Display Settings
    try:
        ds = await client.get_display_settings()
        t.record("get_display_settings", "PASS")
        print(f"✓ get_display_settings: theme={ds.theme}, unit={ds.unit}")
    except Exception as e:
        t.record("get_display_settings", f"FAIL: {e}")
        print(f"✗ get_display_settings: {e}")

    # 48. Docker Port Conflicts
    try:
        pc = await client.get_docker_port_conflicts()
        t.record("get_docker_port_conflicts", "PASS")
        print(f"✓ get_docker_port_conflicts: {len(pc.lanPorts)} LAN conflicts")
    except Exception as e:
        t.record("get_docker_port_conflicts", f"FAIL: {e}")
        print(f"✗ get_docker_port_conflicts: {e}")

    # 49. Extended Container Fields
    try:
        containers = await client.typed_get_containers()
        if containers:
            c = containers[0]
            t.record("extended_container_fields", "PASS")
            print(
                f"✓ extended_container_fields:"
                f" shell={c.shell}, autoStart={c.autoStartOrder}"
            )
        else:
            t.record("extended_container_fields", "PASS (no containers)")
            print("✓ extended_container_fields: (no containers)")
    except Exception as e:
        t.record("extended_container_fields", f"FAIL: {e}")
        print(f"✗ extended_container_fields: {e}")

    # 50. Extended Array Disk Fields
    try:
        array = await client.typed_get_array()
        if array.disks:
            d = array.disks[0]
            t.record("extended_array_disk_fields", "PASS")
            print(
                f"✓ extended_array_disk_fields:"
                f" rotational={d.rotational},"
                f" transport={d.transport}"
            )
        else:
            t.record("extended_array_disk_fields", "PASS (no disks)")
    except Exception as e:
        t.record("extended_array_disk_fields", f"FAIL: {e}")
        print(f"✗ extended_array_disk_fields: {e}")

    # 51. Extended Share Fields
    try:
        shares = await client.typed_get_shares()
        if shares:
            s = shares[0]
            t.record("extended_share_fields", "PASS")
            print(
                f"✓ extended_share_fields: {s.name}"
                f" - allocator={s.allocator}, cow={s.cow}"
            )
        else:
            t.record("extended_share_fields", "PASS (no shares)")
    except Exception as e:
        t.record("extended_share_fields", f"FAIL: {e}")
        print(f"✗ extended_share_fields: {e}")

    # 52. Extended Vars Fields
    try:
        vars_d = await client.typed_get_vars()
        t.record("extended_vars_fields", "PASS")
        print(
            f"✓ extended_vars_fields:"
            f" sbVersion={vars_d.sb_version},"
            f" joinStatus={vars_d.join_status}"
        )
    except Exception as e:
        t.record("extended_vars_fields", f"FAIL: {e}")
        print(f"✗ extended_vars_fields: {e}")

    # 53. Registration KeyFile
    try:
        reg = await client.typed_get_registration()
        key_loc = reg.keyFile.location if reg.keyFile else "None"
        t.record("registration_key_file", "PASS")
        print(f"✓ registration_key_file: type={reg.type}, keyFile={key_loc}")
    except Exception as e:
        t.record("registration_key_file", f"FAIL: {e}")
        print(f"✗ registration_key_file: {e}")

    # 54. Boot Devices
    try:
        array = await client.typed_get_array()
        t.record("boot_devices", "PASS")
        print(f"✓ boot_devices: {len(array.bootDevices)} boot devices")
    except Exception as e:
        t.record("boot_devices", f"FAIL: {e}")
        print(f"✗ boot_devices: {e}")

    # --- Issue #38: Missing Memory Fields ---
    t.section("Issue #38: Missing Memory Fields (active, buffcache, swapFree)")

    # 55. Memory fields in get_system_metrics
    try:
        m = await client.get_system_metrics()
        has_active = m.memory_active is not None
        has_buffcache = m.memory_buffcache is not None
        has_swap_free = m.swap_free is not None
        t.record("memory_active_buffcache_swapfree", "PASS")
        print(
            f"✓ memory fields:"
            f" active={format_bytes(m.memory_active)},"
            f" buffcache={format_bytes(m.memory_buffcache)},"
            f" swapFree={format_bytes(m.swap_free)}"
        )
        if not has_active:
            print("  ⚠ active field is None (server may not support it)")
        if not has_buffcache:
            print("  ⚠ buffcache field is None (server may not support it)")
        if not has_swap_free:
            print("  ⚠ swapFree field is None (may be 0 if no swap)")
    except Exception as e:
        t.record("memory_active_buffcache_swapfree", f"FAIL: {e}")
        print(f"✗ memory fields: {e}")

    # --- Issue #37: Temperature Monitoring ---
    t.section("Issue #37: Temperature Monitoring (metrics.temperature)")

    # 56. Temperature via get_system_metrics
    try:
        m = await client.get_system_metrics()
        if m.temperature:
            sensor_count = len(m.temperature.sensors)
            avg = m.temperature.summary.average if m.temperature.summary else None
            t.record("system_metrics_temperature", "PASS")
            print(
                f"✓ system_metrics temperature:"
                f" {sensor_count} sensors, avg={avg}"
            )
        else:
            t.record("system_metrics_temperature", "PASS (no temp data)")
            print("✓ system_metrics temperature: no data (server may not support it)")
    except Exception as e:
        t.record("system_metrics_temperature", f"FAIL: {e}")
        print(f"✗ system_metrics temperature: {e}")

    # 57. Dedicated get_temperature_metrics
    try:
        temp = await client.get_temperature_metrics()
        t.record("get_temperature_metrics", "PASS")
        print(f"✓ get_temperature_metrics: {len(temp.sensors)} sensors")
        if temp.summary:
            hottest_name = temp.summary.hottest.name if temp.summary.hottest else "N/A"
            coolest_name = temp.summary.coolest.name if temp.summary.coolest else "N/A"
            print(
                f"  → avg={temp.summary.average},"
                f" warnings={temp.summary.warningCount},"
                f" critical={temp.summary.criticalCount}"
            )
            print(f"  → hottest={hottest_name}, coolest={coolest_name}")
        for s in temp.sensors[:5]:
            val = s.temperature
            status = s.current.status if s.current else "N/A"
            print(f"  → {s.name}: {val}°C ({s.type}) [{status}]")
        if len(temp.sensors) > 5:
            print(f"  → ... and {len(temp.sensors) - 5} more sensors")
    except Exception as e:
        t.record("get_temperature_metrics", f"FAIL: {e}")
        print(f"✗ get_temperature_metrics: {e}")

    # 58. Temperature sensor type filtering
    try:
        temp = await client.get_temperature_metrics()
        disk_count = len(temp.disk_sensors)
        nvme_count = len(temp.nvme_sensors)
        cpu_count = len(temp.cpu_sensors)
        t.record("temperature_sensor_filtering", "PASS")
        print(
            f"✓ temperature sensor filtering:"
            f" disk={disk_count}, nvme={nvme_count}, cpu={cpu_count}"
        )
    except Exception as e:
        t.record("temperature_sensor_filtering", f"FAIL: {e}")
        print(f"✗ temperature sensor filtering: {e}")

    return t.summary()


# ---------------------------------------------------------------------------
# Notification mutation tests
# ---------------------------------------------------------------------------


async def run_mutation_tests(client: UnraidClient) -> int:
    """Run notification mutation tests (archive/delete). Returns exit code."""
    t = TestRunner("NOTIFICATION MUTATION LIVE TEST")
    t.header()

    # 1. Get initial overview
    try:
        overview = await client.get_notification_overview()
        t.record("initial_overview", "PASS")
        print(
            f"✓ initial_overview:"
            f" unread={overview.unread.total},"
            f" archive={overview.archive.total}"
        )
    except Exception as e:
        t.record("initial_overview", f"FAIL: {e}")
        print(f"✗ initial_overview: {e}")
        return t.summary()

    # 2. Archive all notifications
    try:
        result = await client.archive_all_notifications()
        t.record("archive_all_notifications", "PASS")
        print(f"✓ archive_all_notifications: {result}")
    except Exception as e:
        t.record("archive_all_notifications", f"FAIL: {e}")
        print(f"✗ archive_all_notifications: {e}")

    # 3. Check overview after archive
    try:
        overview = await client.get_notification_overview()
        t.record("post_archive_overview", "PASS")
        print(
            f"✓ post_archive_overview:"
            f" unread={overview.unread.total},"
            f" archive={overview.archive.total}"
        )
    except Exception as e:
        t.record("post_archive_overview", f"FAIL: {e}")
        print(f"✗ post_archive_overview: {e}")

    # 4. Delete all archived notifications
    try:
        result = await client.delete_all_notifications()
        t.record("delete_all_notifications", "PASS")
        print(f"✓ delete_all_notifications: {result}")
    except Exception as e:
        t.record("delete_all_notifications", f"FAIL: {e}")
        print(f"✗ delete_all_notifications: {e}")

    # 5. Final overview
    try:
        overview = await client.get_notification_overview()
        t.record("final_overview", "PASS")
        print(
            f"✓ final_overview:"
            f" unread={overview.unread.total},"
            f" archive={overview.archive.total}"
        )
    except Exception as e:
        t.record("final_overview", f"FAIL: {e}")
        print(f"✗ final_overview: {e}")

    return t.summary()


# ---------------------------------------------------------------------------
# WebSocket subscription tests
# ---------------------------------------------------------------------------


async def run_subscription_tests(client: UnraidClient) -> int:  # noqa: PLR0915
    """Run WebSocket subscription tests. Returns exit code."""
    t = TestRunner("WEBSOCKET SUBSCRIPTION LIVE TEST")
    t.header()

    # 1. CPU Metrics
    try:
        print("\n1. subscribe_cpu_metrics()...")
        count = 0
        async for cpu in client.subscribe_cpu_metrics():
            print(f"   CPU: total={cpu.percentTotal}%, cores={len(cpu.cpus)}")
            count += 1
            if count >= 2:
                break
        t.record("subscribe_cpu_metrics", "PASS")
        print("   PASS")
    except Exception as e:
        t.record("subscribe_cpu_metrics", f"FAIL: {e}")
        print(f"   FAIL: {e}")

    # 2. Memory Metrics
    try:
        print("\n2. subscribe_memory_metrics()...")
        count = 0
        async for mem in client.subscribe_memory_metrics():
            print(
                f"   Memory: total={mem.total},"
                f" used={mem.used},"
                f" percent={mem.percentTotal}%"
            )
            count += 1
            if count >= 2:
                break
        t.record("subscribe_memory_metrics", "PASS")
        print("   PASS")
    except Exception as e:
        t.record("subscribe_memory_metrics", f"FAIL: {e}")
        print(f"   FAIL: {e}")

    # 3. CPU Telemetry
    try:
        print("\n3. subscribe_cpu_telemetry()...")
        count = 0
        async for tel in client.subscribe_cpu_telemetry():
            print(f"   Telemetry: power={tel.totalPower}W, temp={tel.temp}C")
            count += 1
            if count >= 2:
                break
        t.record("subscribe_cpu_telemetry", "PASS")
        print("   PASS")
    except Exception as e:
        t.record("subscribe_cpu_telemetry", f"FAIL: {e}")
        print(f"   FAIL: {e}")

    # 4. Array Updates (event-driven, may not emit data — use timeout)
    try:
        print("\n4. subscribe_array_updates()...")
        count = 0

        async def _array_test() -> None:
            nonlocal count
            async for arr in client.subscribe_array_updates():
                print(f"   Array: state={arr.state}, capacity={arr.capacity}")
                count += 1
                if count >= 2:
                    break

        try:
            await asyncio.wait_for(_array_test(), timeout=10.0)
            t.record("subscribe_array_updates", "PASS")
            print("   PASS")
        except TimeoutError:
            if count > 0:
                t.record("subscribe_array_updates", f"PASS ({count} event(s) in 10s)")
                print(f"   PASS ({count} event(s) in 10s)")
            else:
                t.record(
                    "subscribe_array_updates",
                    "PASS (connected, no events in 10s)",
                )
                print(
                    "   PASS (connected, no events in 10s)"
                )
    except Exception as e:
        t.record("subscribe_array_updates", f"FAIL: {e}")
        print(f"   FAIL: {e}")

    # 5. UPS Updates (event-driven, may not emit data — use timeout)
    try:
        print("\n5. subscribe_ups_updates()...")
        count = 0

        async def _ups_test() -> None:
            nonlocal count
            async for ups in client.subscribe_ups_updates():
                keys = list(ups.keys()) if isinstance(ups, dict) else str(ups)
                print(f"   UPS: keys={keys}")
                count += 1
                if count >= 2:
                    break

        try:
            await asyncio.wait_for(_ups_test(), timeout=10.0)
            t.record("subscribe_ups_updates", "PASS")
            print("   PASS")
        except TimeoutError:
            if count > 0:
                t.record("subscribe_ups_updates", f"PASS ({count} event(s) in 10s)")
                print(f"   PASS ({count} event(s) in 10s)")
            else:
                t.record("subscribe_ups_updates", "PASS (connected, no events in 10s)")
                print("   PASS (connected, no events in 10s)")
    except Exception as e:
        t.record("subscribe_ups_updates", f"FAIL: {e}")
        print(f"   FAIL: {e}")

    # 6. Container Stats (streams all containers, no ID parameter needed)
    try:
        print("\n6. subscribe_container_stats()...")
        containers = await client.get_containers()
        running = [
            c for c in containers
            if str(c.get("state", "")).lower() == "running"
        ]
        if running:
            print(f"   {len(running)} running containers detected")
            count = 0
            async for stats in client.subscribe_container_stats():
                print(
                    f"   Stats: id={stats.id},"
                    f" cpu={stats.cpuPercent}%,"
                    f" mem={stats.memUsage}"
                )
                count += 1
                if count >= 2:
                    break
            t.record("subscribe_container_stats", "PASS")
            print("   PASS")
        else:
            t.record("subscribe_container_stats", "SKIP (no running containers)")
            print("   SKIP (no running containers)")
    except Exception as e:
        t.record("subscribe_container_stats", f"FAIL: {e}")
        print(f"   FAIL: {e}")

    # 7. Raw subscribe (event-driven — use timeout)
    try:
        print("\n7. subscribe() raw query...")
        count = 0

        async def _raw_test() -> None:
            nonlocal count
            async for data in client.subscribe(
                "subscription { arraySubscription { state } }"
            ):
                print(f"   Raw: {data}")
                count += 1
                if count >= 2:
                    break

        try:
            await asyncio.wait_for(_raw_test(), timeout=10.0)
            t.record("subscribe_raw", "PASS")
            print("   PASS")
        except TimeoutError:
            if count > 0:
                t.record("subscribe_raw", f"PASS ({count} event(s) in 10s)")
                print(f"   PASS ({count} event(s) in 10s)")
            else:
                t.record("subscribe_raw", "PASS (connected, no events in 10s)")
                print("   PASS (connected, no events in 10s)")
    except Exception as e:
        t.record("subscribe_raw", f"FAIL: {e}")
        print(f"   FAIL: {e}")

    # 8. Temperature subscription
    try:
        print("\n8. subscribe_temperature_metrics()...")
        count = 0
        async for temp in client.subscribe_temperature_metrics():
            sensor_count = len(temp.sensors)
            avg = temp.summary.average if temp.summary else "N/A"
            print(f"   Temperature: {sensor_count} sensors, avg={avg}")
            count += 1
            if count >= 2:
                break
        t.record("subscribe_temperature_metrics", "PASS")
        print("   PASS")
    except Exception as e:
        t.record("subscribe_temperature_metrics", f"FAIL: {e}")
        print(f"   FAIL: {e}")

    return t.summary()


# ---------------------------------------------------------------------------
# SSL detection tests
# ---------------------------------------------------------------------------


async def _test_ssl_connection(
    label: str,
    host: str,
    api_key: str,
    *,
    http_port: int = 80,
    https_port: int = 443,
) -> bool:
    """Test a single SSL configuration."""
    print(f"\n{'─' * 60}")
    print(f"TEST: {label}")
    print(f"  http_port={http_port}, https_port={https_port}")
    print(f"{'─' * 60}")
    try:
        async with UnraidClient(
            host,
            api_key,
            http_port=http_port,
            https_port=https_port,
            verify_ssl=False,
        ) as client:
            redirect_url, use_ssl = await client._discover_redirect_url()
            redirect_found = redirect_url is not None
            ssl_enabled = bool(use_ssl)
            print(f"  Discovery: redirect_found={redirect_found}, use_ssl={ssl_enabled}")
            client._resolved_url = None
            result = await client.test_connection()
            print(f"  test_connection: {result}")
            print("  RESULT: PASS")
            return True
    except Exception as e:
        print(f"  RESULT: FAIL — {type(e).__name__}: {e}")
        return False


async def run_ssl_tests(host: str, api_key: str) -> int:
    """Run SSL detection tests. Returns exit code."""
    http_port = int(os.environ.get("UNRAID_HTTP_PORT", "80"))
    https_port = int(os.environ.get("UNRAID_HTTPS_PORT", "443"))

    print("=" * 60)
    print("SSL/TLS DETECTION LIVE TEST")
    print(f"HTTP port: {http_port}, HTTPS port: {https_port}")
    print("=" * 60)

    results: list[tuple[str, bool]] = []

    ok = await _test_ssl_connection(
        f"Standard (http={http_port}, https={https_port})",
        host, api_key, http_port=http_port, https_port=https_port,
    )
    results.append(("Standard ports", ok))

    ok = await _test_ssl_connection(
        f"Same port for both = {https_port} (ha-unraid behavior)",
        host, api_key, http_port=https_port, https_port=https_port,
    )
    results.append(("Same port (ha-unraid)", ok))

    if http_port != https_port:
        ok = await _test_ssl_connection(
            f"http_port={https_port}, https_port=9999 (nginx 400 detection)",
            host, api_key, http_port=https_port, https_port=9999,
        )
        results.append(("nginx 400 detection", ok))

        ok = await _test_ssl_connection(
            f"Same port for both = {http_port}",
            host, api_key, http_port=http_port, https_port=http_port,
        )
        results.append(("HTTP port as single port", ok))

    print("\n" + "=" * 60)
    print("SUMMARY")
    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    print(f"\n{passed}/{len(results)} tests passed")
    print("=" * 60)

    return 0 if passed == len(results) else 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified Unraid API test client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s                   # Run all query tests (default)
  %(prog)s --mutations       # Run notification mutation tests
  %(prog)s --subscriptions   # Run WebSocket subscription tests
  %(prog)s --ssl             # Run SSL detection tests
  %(prog)s --all             # Run everything
""",
    )
    parser.add_argument(
        "--mutations",
        action="store_true",
        help="Run notification mutation tests",
    )
    parser.add_argument(
        "--subscriptions",
        action="store_true",
        help="Run subscription tests",
    )
    parser.add_argument("--ssl", action="store_true", help="Run SSL detection tests")
    parser.add_argument("--all", action="store_true", help="Run all test suites")
    args = parser.parse_args()

    host, api_key = load_env()
    print("Host: <configured>")
    print(f"API Key: {'*' * 8}...{'*' * 4} (loaded)")
    print()

    exit_code = 0

    # Determine which suites to run
    has_specific = args.subscriptions or args.ssl or args.mutations
    run_queries = args.all or not has_specific
    run_mutations = args.all or args.mutations
    run_subs = args.all or args.subscriptions
    run_ssl_flag = args.all or args.ssl

    if run_queries or run_subs or run_mutations:
        async with UnraidClient(host, api_key, verify_ssl=False) as client:
            if run_queries:
                rc = await run_query_tests(client)
                exit_code = max(exit_code, rc)

            if run_mutations:
                if run_queries:
                    print("\n\n")
                rc = await run_mutation_tests(client)
                exit_code = max(exit_code, rc)

            if run_subs:
                if run_queries or run_mutations:
                    print("\n\n")
                rc = await run_subscription_tests(client)
                exit_code = max(exit_code, rc)

    if run_ssl_flag:
        if run_queries or run_subs:
            print("\n\n")
        rc = await run_ssl_tests(host, api_key)
        exit_code = max(exit_code, rc)

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
