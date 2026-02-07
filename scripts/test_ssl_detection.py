#!/usr/bin/env python3
"""Live SSL/TLS detection test for all _discover_redirect_url code paths.

Usage:
    UNRAID_HOST=192.168.1.100 UNRAID_API_KEY=your-key python scripts/test_ssl_detection.py

The script will prompt you to change Unraid SSL settings between tests.
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, "src")

from unraid_api import UnraidClient

logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
_LOGGER = logging.getLogger("unraid_api")


async def test_connection(
    label: str,
    host: str,
    api_key: str,
    *,
    http_port: int = 80,
    https_port: int = 443,
) -> bool:
    """Test a single SSL configuration and report results."""
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
            # Step 1: Check discovery
            redirect_url, use_ssl = await client._discover_redirect_url()
            print(f"  Discovery result: redirect_url={redirect_url}, use_ssl={use_ssl}")

            # Reset so query triggers full flow
            client._resolved_url = None

            # Step 2: Make a real query
            result = await client.test_connection()
            print(f"  Resolved URL: {client._resolved_url}")
            print(f"  test_connection: {result}")
            print(f"  RESULT: PASS")
            return True
    except Exception as e:
        print(f"  RESULT: FAIL - {type(e).__name__}: {e}")
        return False


async def main() -> None:
    host = os.environ.get("UNRAID_HOST", "")
    api_key = os.environ.get("UNRAID_API_KEY", "")

    if not host or not api_key:
        print("ERROR: Set UNRAID_HOST and UNRAID_API_KEY environment variables")
        print(
            "Usage: UNRAID_HOST=x.x.x.x UNRAID_API_KEY=your-key "
            "python scripts/test_ssl_detection.py"
        )
        sys.exit(1)

    # Read ports from env or use defaults
    http_port = int(os.environ.get("UNRAID_HTTP_PORT", "80"))
    https_port = int(os.environ.get("UNRAID_HTTPS_PORT", "443"))

    print("=" * 60)
    print("SSL/TLS DETECTION LIVE TEST")
    print(f"Host: {host}")
    print(f"Unraid HTTP port: {http_port}")
    print(f"Unraid HTTPS port: {https_port}")
    print("=" * 60)

    results = []

    # --- Test group based on current Unraid SSL setting ---
    print("\nThese tests use the CURRENT Unraid SSL/port settings.")
    print("Run the script once per SSL mode, changing settings in between.\n")

    # Test 1: Standard - use configured ports as-is
    ok = await test_connection(
        f"Standard (http_port={http_port}, https_port={https_port})",
        host,
        api_key,
        http_port=http_port,
        https_port=https_port,
    )
    results.append(("Standard ports", ok))

    # Test 2: Same port for both (simulates ha-unraid passing single port)
    # Use the HTTPS port since that's what users typically enter
    ok = await test_connection(
        f"Same port for both = {https_port} (ha-unraid behavior)",
        host,
        api_key,
        http_port=https_port,
        https_port=https_port,
    )
    results.append(("Same port (ha-unraid)", ok))

    # Test 3: http_port pointing to the HTTPS port (nginx 400 path)
    # This sends an HTTP probe to the HTTPS port with a different https_port
    if http_port != https_port:
        ok = await test_connection(
            f"http_port={https_port}, https_port=9999 (nginx 400 detection)",
            host,
            api_key,
            http_port=https_port,
            https_port=9999,
        )
        results.append(("nginx 400 detection", ok))

    # Test 4: Only HTTP port (if different from HTTPS)
    if http_port != https_port:
        ok = await test_connection(
            f"Same port for both = {http_port} (HTTP port as single port)",
            host,
            api_key,
            http_port=http_port,
            https_port=http_port,
        )
        results.append(("HTTP port as single port", ok))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")

    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{total} tests passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
