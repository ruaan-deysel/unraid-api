# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## Project Overview

`unraid-api` is an async Python client library for Unraid's GraphQL API. Primary consumer is the [ha-unraid](https://github.com/ruaan-deysel/ha-unraid) Home Assistant integration.

## Development Commands

```bash
# Setup
uv sync --all-extras

# Run all tests with coverage
uv run pytest tests/ -v --cov=src/unraid_api

# Run a single test file
uv run pytest tests/test_client.py -v

# Run a single test
uv run pytest tests/test_client.py::TestClassName::test_method_name -v

# Linting and formatting
uv run ruff check .
uv run ruff format .
uv run mypy src/

# Pre-commit hooks (runs ruff, mypy, security checks)
uv run pre-commit run --all-files
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
