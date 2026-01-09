# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`unraid-api` is an async Python client library for Unraid's GraphQL API (v4.21.0+, Unraid 7.1.4+). Primary consumer is the [ha-unraid](https://github.com/ruaan-deysel/ha-unraid) Home Assistant integration.

## Development Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run all tests with coverage
pytest tests/ -v --cov=src/unraid_api

# Run a single test file
pytest tests/test_client.py -v

# Run a single test
pytest tests/test_client.py::TestClassName::test_method_name -v

# Linting and formatting
ruff check .
ruff format .
mypy src/

# Pre-commit hooks (runs ruff, mypy, security checks)
pre-commit run --all-files
```

## Architecture

```
src/unraid_api/
├── __init__.py      # Public exports, version
├── client.py        # UnraidClient - async GraphQL client with SSL auto-discovery
├── models.py        # Pydantic response models (UnraidBaseModel ignores unknown fields)
└── exceptions.py    # UnraidAPIError hierarchy (Connection, Auth, Timeout)
```

### Client Design
- **Async context manager**: `async with UnraidClient(host, api_key) as client:`
- **Session injection**: Accepts external `aiohttp.ClientSession` for HA integration (won't be closed by client)
- **SSL auto-discovery**: Handles Unraid's "No", "Yes", and "Strict" SSL modes via redirect detection
- **GraphQL variables**: Always use variables, never string interpolation for security

### Key Patterns

**GraphQL mutations use PrefixedID type:**
```python
mutation = """
    mutation StartContainer($id: PrefixedID!) {
        docker { start(id: $id) { id state } }
    }
"""
await self.mutate(mutation, {"id": container_id})
```

**Pydantic models extend UnraidBaseModel for forward compatibility:**
```python
class ArrayDisk(UnraidBaseModel):
    id: str
    name: str | None = None
```

### Disk Standby Awareness
- `get_array_status()` and `get_array_disks()` do NOT wake sleeping disks (safe for polling)
- `get_physical_disks()` WILL wake sleeping disks (use sparingly)
- Check `isSpinning` field; `temp` is null/0 for standby disks

## Test Requirements
- TDD: Write tests first
- Minimum 80% coverage
- Use `pytest-asyncio` with `asyncio_mode = "auto"`
- Mock fixtures in `tests/conftest.py`

## GraphQL Reference
See `UNRAIDAPI.md` for available fields and schema documentation.
