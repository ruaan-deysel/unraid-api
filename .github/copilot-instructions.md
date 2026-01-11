# Copilot Instructions for unraid-api

## Project Overview

`unraid-api` is an async Python client library (PyPI package) for Unraid's official GraphQL API (v4.21.0+, Unraid 7.1.4+). Primary consumer is the [ha-unraid](https://github.com/ruaan-deysel/ha-unraid) Home Assistant integration.

## Critical Requirements

### Test-Driven Development (TDD)
- **Every feature MUST have tests written FIRST** before implementation
- Test files live in `tests/` directory, mirroring source structure
- Use `pytest` with `pytest-asyncio` for async tests
- Run tests: `pytest tests/ -v --cov=src/unraid_api`
- Minimum coverage target: 80%

### Zero Tolerance for Linting
- **No linting warnings or errors allowed**
- Tools: `ruff` for linting/formatting, `mypy` for type checking
- Run before committing: `ruff check . && ruff format --check . && mypy src/`
- All functions must have type hints

### Security Requirements
- **Never hardcode credentials** - use environment variables or secure config
- **Never log sensitive data** (API keys, passwords, tokens)
- Use GraphQL variables for all parameters (never string interpolation)
- Validate all user inputs before use
- Keep dependencies updated for security patches

## Architecture

```
unraid-api/
├── src/unraid_api/          # Package source
│   ├── __init__.py          # Public exports
│   ├── client.py            # UnraidClient async class
│   ├── models.py            # Pydantic response models
│   ├── exceptions.py        # Custom exception hierarchy
│   └── py.typed             # PEP 561 marker
├── tests/                   # Test files
│   ├── conftest.py          # Shared fixtures
│   ├── test_client.py       # Client tests
│   ├── test_models.py       # Model tests
│   └── test_exceptions.py   # Exception tests
├── pyproject.toml           # Package config, all tool settings
└── UNRAIDAPI.md             # GraphQL schema reference
```

### Client Design Pattern
- **Async-first**: Uses `aiohttp` for all HTTP operations
- **Context manager**: `async with UnraidClient(...) as client:`
- **Queries** → `get_*` methods or direct `query()` calls
- **Mutations** → action methods (`start_*`, `stop_*`) or `mutate()` calls
- **Session injection**: Accepts external `aiohttp.ClientSession` for HA integration

### Exception Hierarchy
```
UnraidAPIError (base)
├── UnraidConnectionError   # Network failures
├── UnraidAuthenticationError  # Invalid API key
└── UnraidTimeoutError      # Request timeout
```

## Code Conventions

### GraphQL with Variables (Security Pattern)
Always use GraphQL variables - never string interpolation:
```python
async def start_container(self, container_id: str) -> dict[str, Any]:
    """Start a Docker container."""
    mutation = """
        mutation StartContainer($id: PrefixedID!) {
            docker {
                start(id: $id) { id state }
            }
        }
    """
    return await self.mutate(mutation, {"id": container_id})
```

### Pydantic Models
Use `UnraidBaseModel` for forward compatibility (ignores unknown fields):
```python
class ArrayDisk(UnraidBaseModel):
    id: str
    name: str | None = None
    temp: int | None = None
```

### Test Pattern
```python
class TestClientInitialization:
    def test_init_with_required_params(self, host: str, api_key: str) -> None:
        """Test client initialization with required parameters."""
        client = UnraidClient(host, api_key)
        assert client.host == host
```

## Developer Workflow

### Setup
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

### Pre-commit Checklist
```bash
pytest tests/ -v --cov=src/unraid_api
ruff check .
ruff format .
mypy src/
```

**Pre-commit MUST always be run before any commit.**

### Usage Example
```python
from unraid_api import UnraidClient

async with UnraidClient("192.168.1.100", "your-api-key") as client:
    if await client.test_connection():
        version = await client.get_version()
        print(f"Unraid {version['unraid']}, API {version['api']}")
```

## Adding New Features

1. **Write tests first** in `tests/` for the new functionality
2. Add method to `client.py` following async patterns
3. Add Pydantic models to `models.py` if needed
4. Use GraphQL variables for all parameters
5. Add type hints to all parameters and return values
6. Reference `UNRAIDAPI.md` for available GraphQL fields
7. Run full lint/test suite before committing
8. **Update documentation** (see Documentation Requirements below)
9. **Update version numbers** (see Versioning below)

## Documentation Requirements

**README.md and CHANGELOG.md MUST always be kept up to date.**

### README.md
- Update API Reference tables when adding new methods
- Update Models section when adding new Pydantic models
- Keep usage examples current and working

### CHANGELOG.md
- Follow [Keep a Changelog](https://keepachangelog.com) format
- Add entries under `[Unreleased]` section during development
- Categories: Added, Changed, Deprecated, Removed, Fixed, Security
- Move entries to versioned section on release

## Versioning

**Version numbers MUST be updated when new features or bug fixes are made.**

### Semantic Versioning
- **MAJOR** (X.0.0): Breaking API changes
- **MINOR** (0.X.0): New features, backward compatible
- **PATCH** (0.0.X): Bug fixes, backward compatible

### Version Locations (update ALL)
1. `pyproject.toml` → `version = "X.Y.Z"`
2. `src/unraid_api/__init__.py` → `__version__ = "X.Y.Z"`

### When to Bump
- **New methods/models**: MINOR version bump
- **Bug fixes**: PATCH version bump
- **Breaking changes**: MAJOR version bump (rare)

## Dependencies

Core: `aiohttp>=3.9.0`, `pydantic>=2.0.0`
Dev: `pytest`, `pytest-asyncio`, `pytest-cov`, `aioresponses`, `ruff`, `mypy`
