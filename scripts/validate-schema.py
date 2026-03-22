#!/usr/bin/env python3
"""Unraid API ↔ GraphQL Schema Cross-Check Validator.

This script validates that every GraphQL query, mutation, and subscription
in the unraid-api client library is compatible with the actual schema
exposed by a live Unraid server AND the official schema from the Unraid
API GitHub repository. It catches field renames, removed fields, changed
nesting (e.g., the capacity { kilobytes { ... } } issue from #196), and
type mismatches BEFORE they hit production.

Three-way cross-check:
  Official GitHub Schema ↔ Live Server ↔ Our Client

How it works:
  1. Fetches the official GraphQL SDL schema from github.com/unraid/api
  2. Introspects the live Unraid GraphQL schema to get all types and fields
  3. Extracts all GraphQL operation strings from the client source code
  4. Validates every requested field exists on BOTH schemas
  5. Compares official schema vs live server to detect drift
  6. Runs every client method against the live server
  7. Validates response data matches Pydantic models
  8. Reports any schema mismatches, missing fields, or validation errors

Usage:
  python scripts/validate-schema.py                 # Run all validations
  python scripts/validate-schema.py --schema-only   # Only introspect + validate fields
  python scripts/validate-schema.py --live-only     # Only run live method tests
  python scripts/validate-schema.py --github-only   # Only fetch + validate against GitHub schema
  python scripts/validate-schema.py --no-github     # Skip GitHub schema check
  python scripts/validate-schema.py --dump-schema   # Dump introspected schema to JSON

Reads credentials from scripts/.env or UNRAID_HOST/UNRAID_API_KEY env vars.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import re
import sys
import textwrap
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure the local src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from unraid_api import UnraidClient  # noqa: E402


# =============================================================================
# Credential Loading
# =============================================================================


def _sanitize_host(host: str) -> str:
    if "://" in host:
        from urllib.parse import urlparse

        parsed = urlparse(host)
        return parsed.hostname or "***"
    if "@" in host:
        return host.split("@", 1)[1]
    return host


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


# =============================================================================
# Schema Introspection
# =============================================================================

# Unraid blocks __schema introspection but allows __type queries.
# We use __type to introspect individual types, starting from known roots
# and recursively following field types.

INTROSPECTION_TYPE_QUERY = """
query IntrospectType($name: String!) {
    __type(name: $name) {
        kind
        name
        fields {
            name
            args {
                name
                type {
                    kind
                    name
                    ofType {
                        kind
                        name
                        ofType { kind name ofType { kind name } }
                    }
                }
            }
            type {
                kind
                name
                ofType {
                    kind
                    name
                    ofType { kind name ofType { kind name } }
                }
            }
        }
        inputFields {
            name
            type {
                kind
                name
                ofType { kind name ofType { kind name } }
            }
        }
        enumValues { name }
    }
}
"""


@dataclass
class SchemaField:
    """A field in a GraphQL type."""

    name: str
    type_name: str | None
    type_kind: str
    is_list: bool = False
    is_non_null: bool = False
    args: list[str] = field(default_factory=list)


@dataclass
class SchemaType:
    """A GraphQL type with its fields."""

    name: str
    kind: str
    fields: dict[str, SchemaField] = field(default_factory=dict)
    enum_values: list[str] = field(default_factory=list)


def _unwrap_type(type_info: dict[str, Any]) -> tuple[str | None, str, bool, bool]:
    """Unwrap a GraphQL type to get the base type name."""
    is_non_null = False
    is_list = False
    current = type_info

    while current:
        kind = current.get("kind", "")
        name = current.get("name")

        if kind == "NON_NULL":
            is_non_null = True
            current = current.get("ofType", {})
        elif kind == "LIST":
            is_list = True
            current = current.get("ofType", {})
        else:
            return name, kind, is_list, is_non_null

    return None, "UNKNOWN", is_list, is_non_null


def parse_schema(introspection_result: dict[str, Any]) -> dict[str, SchemaType]:
    """Parse introspection result into a type map."""
    schema_data = introspection_result.get("__schema", {})
    types: dict[str, SchemaType] = {}

    for type_data in schema_data.get("types", []):
        name = type_data.get("name", "")
        if name.startswith("__"):
            continue  # Skip introspection types

        schema_type = SchemaType(
            name=name,
            kind=type_data.get("kind", ""),
        )

        # Parse fields
        for field_data in type_data.get("fields") or []:
            field_name = field_data.get("name", "")
            type_info = field_data.get("type", {})
            type_name, type_kind, is_list, is_non_null = _unwrap_type(type_info)
            args = [a.get("name", "") for a in (field_data.get("args") or [])]

            schema_type.fields[field_name] = SchemaField(
                name=field_name,
                type_name=type_name,
                type_kind=type_kind,
                is_list=is_list,
                is_non_null=is_non_null,
                args=args,
            )

        # Parse enum values
        for ev in type_data.get("enumValues") or []:
            schema_type.enum_values.append(ev.get("name", ""))

        types[name] = schema_type

    return types


async def introspect_schema(client: UnraidClient) -> dict[str, SchemaType]:
    """Crawl the GraphQL schema by introspecting types starting from roots.

    Since Unraid blocks __schema introspection, we use __type queries
    to walk from Query/Mutation/Subscription roots through all reachable types.
    """
    types: dict[str, SchemaType] = {}
    queue: list[str] = ["Query", "Mutation", "Subscription"]
    visited: set[str] = set()

    while queue:
        type_name = queue.pop(0)
        if type_name in visited or type_name.startswith("__"):
            continue
        visited.add(type_name)

        try:
            result = await client.query(
                INTROSPECTION_TYPE_QUERY, {"name": type_name}
            )
        except Exception as e:
            print(f"  WARNING: Could not introspect '{type_name}': {e}")
            continue

        type_data = result.get("__type")
        if type_data is None:
            continue

        schema_type = SchemaType(
            name=type_data.get("name", type_name),
            kind=type_data.get("kind", ""),
        )

        for field_data in type_data.get("fields") or []:
            field_name = field_data.get("name", "")
            type_info = field_data.get("type", {})
            f_type_name, type_kind, is_list, is_non_null = _unwrap_type(type_info)
            args = [a.get("name", "") for a in (field_data.get("args") or [])]
            schema_type.fields[field_name] = SchemaField(
                name=field_name,
                type_name=f_type_name,
                type_kind=type_kind,
                is_list=is_list,
                is_non_null=is_non_null,
                args=args,
            )

            # Queue the field's type for introspection if it's an object type
            if f_type_name and f_type_name not in visited:
                queue.append(f_type_name)

        for ev in type_data.get("enumValues") or []:
            schema_type.enum_values.append(ev.get("name", ""))

        types[type_name] = schema_type

    print(f"  Crawled {len(types)} types from schema")
    return types


# =============================================================================
# Official GitHub Schema — Fetch & Parse SDL
# =============================================================================

GITHUB_SCHEMA_URL = (
    "https://raw.githubusercontent.com/unraid/api/main"
    "/api/generated-schema.graphql"
)


def fetch_official_schema_sdl(
    url: str = GITHUB_SCHEMA_URL,
    branch: str | None = None,
) -> str:
    """Fetch the generated-schema.graphql from the official Unraid API repo."""
    if branch:
        url = url.replace("/main/", f"/{branch}/")
    req = urllib.request.Request(url, headers={"User-Agent": "unraid-api-validator"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return resp.read().decode("utf-8")


def parse_sdl_to_schema_types(sdl_text: str) -> dict[str, SchemaType]:
    """Parse a GraphQL SDL string into our SchemaType format.

    Uses graphql-core to build a proper schema, then converts to the same
    data structures used by live introspection so all comparison logic
    can be reused.
    """
    from graphql import build_schema as gql_build_schema
    from graphql import (
        GraphQLEnumType,
        GraphQLField,
        GraphQLInputObjectType,
        GraphQLList,
        GraphQLNonNull,
        GraphQLObjectType,
        GraphQLUnionType,
    )

    # Build schema — use assume_valid to tolerate custom scalars
    schema = gql_build_schema(sdl_text, assume_valid=True)
    types: dict[str, SchemaType] = {}

    def _unwrap_gql_type(
        gql_type: Any,
    ) -> tuple[str | None, str, bool, bool]:
        """Unwrap a graphql-core type to (name, kind, is_list, is_non_null)."""
        is_non_null = False
        is_list = False
        current = gql_type

        while current is not None:
            if isinstance(current, GraphQLNonNull):
                is_non_null = True
                current = current.of_type
            elif isinstance(current, GraphQLList):
                is_list = True
                current = current.of_type
            else:
                name = getattr(current, "name", None)
                if isinstance(current, GraphQLObjectType):
                    kind = "OBJECT"
                elif isinstance(current, GraphQLEnumType):
                    kind = "ENUM"
                elif isinstance(current, GraphQLInputObjectType):
                    kind = "INPUT_OBJECT"
                elif isinstance(current, GraphQLUnionType):
                    kind = "UNION"
                else:
                    kind = "SCALAR"
                return name, kind, is_list, is_non_null

        return None, "UNKNOWN", is_list, is_non_null

    for type_name, gql_type in schema.type_map.items():
        if type_name.startswith("__"):
            continue

        if isinstance(gql_type, GraphQLObjectType):
            kind = "OBJECT"
        elif isinstance(gql_type, GraphQLEnumType):
            kind = "ENUM"
        elif isinstance(gql_type, GraphQLInputObjectType):
            kind = "INPUT_OBJECT"
        elif isinstance(gql_type, GraphQLUnionType):
            kind = "UNION"
        else:
            kind = "SCALAR"

        st = SchemaType(name=type_name, kind=kind)

        # Extract fields
        if isinstance(
            gql_type, (GraphQLObjectType, GraphQLInputObjectType)
        ):
            field_map: dict[str, GraphQLField] = gql_type.fields
            for fname, fval in field_map.items():
                f_type_name, f_kind, f_is_list, f_is_non_null = _unwrap_gql_type(
                    fval.type
                )
                args_list: list[str] = []
                if hasattr(fval, "args") and fval.args:
                    args_list = list(fval.args.keys())
                st.fields[fname] = SchemaField(
                    name=fname,
                    type_name=f_type_name,
                    type_kind=f_kind,
                    is_list=f_is_list,
                    is_non_null=f_is_non_null,
                    args=args_list,
                )

        # Extract enum values
        if isinstance(gql_type, GraphQLEnumType):
            st.enum_values = list(gql_type.values.keys())

        types[type_name] = st

    return types


# =============================================================================
# Official ↔ Live Schema Comparison
# =============================================================================


@dataclass
class SchemaDiffIssue:
    """A difference between the official and live schemas."""

    severity: str  # ERROR, WARNING, INFO
    category: str  # type_missing, field_missing, field_type_mismatch, field_extra
    message: str


def compare_official_vs_live(
    official: dict[str, SchemaType],
    live: dict[str, SchemaType],
) -> list[SchemaDiffIssue]:
    """Compare the official GitHub schema against the live server schema.

    Finds types/fields in official but not live (server behind), and
    types/fields in live but not official (server ahead / custom).
    Only compares OBJECT and INPUT_OBJECT types we care about.
    """
    issues: list[SchemaDiffIssue] = []

    # Skip internal/scalar types for comparison
    skip_kinds = {"SCALAR"}

    # Types in official but not live
    for type_name, otype in official.items():
        if otype.kind in skip_kinds:
            continue
        if type_name not in live:
            issues.append(
                SchemaDiffIssue(
                    severity="WARNING",
                    category="type_missing_on_live",
                    message=(
                        f"Type '{type_name}' ({otype.kind}) exists in official"
                        f" schema but not on live server"
                    ),
                )
            )
            continue

        ltype = live[type_name]

        # Compare fields
        if otype.kind in ("OBJECT", "INPUT_OBJECT"):
            for fname in otype.fields:
                if fname not in ltype.fields:
                    issues.append(
                        SchemaDiffIssue(
                            severity="WARNING",
                            category="field_missing_on_live",
                            message=(
                                f"Field '{type_name}.{fname}' exists in"
                                f" official schema but not on live server"
                            ),
                        )
                    )

    # Types in live but not official
    for type_name, ltype in live.items():
        if ltype.kind in skip_kinds:
            continue
        if type_name not in official:
            issues.append(
                SchemaDiffIssue(
                    severity="INFO",
                    category="type_extra_on_live",
                    message=(
                        f"Type '{type_name}' ({ltype.kind}) exists on live"
                        f" server but not in official schema"
                    ),
                )
            )
            continue

        otype = official[type_name]

        # Fields in live but not official
        if ltype.kind in ("OBJECT", "INPUT_OBJECT"):
            for fname in ltype.fields:
                if fname not in otype.fields:
                    issues.append(
                        SchemaDiffIssue(
                            severity="INFO",
                            category="field_extra_on_live",
                            message=(
                                f"Field '{type_name}.{fname}' exists on live"
                                f" server but not in official schema"
                            ),
                        )
                    )

    return issues


# =============================================================================
# GraphQL Query Extraction from Source Code
# =============================================================================


@dataclass
class ExtractedQuery:
    """A GraphQL query extracted from the client source."""

    method_name: str
    operation_type: str  # query, mutation, subscription
    query_string: str
    line_number: int


def _reconstruct_fstring(node: ast.JoinedStr) -> str:
    """Reconstruct an f-string, replacing interpolated expressions with placeholders."""
    parts = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        else:
            # Replace interpolated expressions with a dummy field name
            # that won't affect GraphQL parsing
            parts.append("")
    return "".join(parts)


def extract_queries_from_source(client_path: str) -> list[ExtractedQuery]:
    """Extract all GraphQL queries from the client.py source code.

    Uses AST parsing to find all string assignments that look like GraphQL operations.
    Handles both regular strings and f-strings.
    """
    source = Path(client_path).read_text()
    tree = ast.parse(source)
    queries: list[ExtractedQuery] = []

    # Collect all JoinedStr node ids so we can skip their child Constants
    fstring_constant_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for child in ast.walk(node):
                if isinstance(child, ast.Constant):
                    fstring_constant_ids.add(id(child))

    # Walk the AST to find method definitions
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        method_name = node.name

        # Find string constants and f-strings that look like GraphQL operations
        for child in ast.walk(node):
            # Handle f-strings
            if isinstance(child, ast.JoinedStr):
                value = _reconstruct_fstring(child).strip()
                lineno = child.lineno
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                # Skip constants that are part of f-strings
                if id(child) in fstring_constant_ids:
                    continue
                value = child.value.strip()
                lineno = child.lineno
            else:
                continue

            # Check if it's a GraphQL operation
            for op_type in ("query", "mutation", "subscription"):
                if value.startswith(op_type) or value.startswith(f"{op_type} "):
                    queries.append(
                        ExtractedQuery(
                            method_name=method_name,
                            operation_type=op_type,
                            query_string=value,
                            line_number=lineno,
                        )
                    )
                    break
            else:
                # Also match anonymous queries like "{ array { ... } }"
                if value.startswith("{") and not value.startswith("{%"):
                    queries.append(
                        ExtractedQuery(
                            method_name=method_name,
                            operation_type="query",
                            query_string=f"query {value}",
                            line_number=lineno,
                        )
                    )

    return queries


# =============================================================================
# GraphQL Field Validation Against Schema
# =============================================================================


@dataclass
class ValidationIssue:
    """A schema validation issue found."""

    method_name: str
    severity: str  # ERROR, WARNING, INFO
    message: str
    field_path: str


def _parse_graphql_selection_set(
    text: str,
) -> list[tuple[str, str | None]]:
    """Simple parser for GraphQL selection sets.

    Returns list of (field_name, sub_selection_text_or_None).
    This is a simplified parser - doesn't handle fragments or aliases.
    """
    results: list[tuple[str, str | None]] = []
    i = 0
    text = text.strip()

    while i < len(text):
        # Skip whitespace and commas
        while i < len(text) and text[i] in " \t\n\r,":
            i += 1
        if i >= len(text):
            break

        # Skip comments
        if text[i] == "#":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue

        # Read field name (may include directives/args)
        field_start = i
        while i < len(text) and text[i] not in " \t\n\r{(,}":
            i += 1
        field_name = text[field_start:i].strip()

        if not field_name or field_name == "...":
            i += 1
            continue

        # Skip arguments ( ... )
        while i < len(text) and text[i] in " \t\n\r":
            i += 1
        if i < len(text) and text[i] == "(":
            depth = 1
            i += 1
            while i < len(text) and depth > 0:
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                i += 1

        # Check for sub-selection { ... }
        while i < len(text) and text[i] in " \t\n\r":
            i += 1
        sub_selection = None
        if i < len(text) and text[i] == "{":
            depth = 1
            start = i + 1
            i += 1
            while i < len(text) and depth > 0:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                i += 1
            sub_selection = text[start : i - 1].strip()

        if field_name and field_name not in ("query", "mutation", "subscription"):
            # Skip aliases: if field_name contains ':', take the part after it
            if ":" in field_name:
                field_name = field_name.split(":", 1)[1].strip()
            results.append((field_name, sub_selection))

    return results


def _extract_body(query_str: str) -> str:
    """Extract the body of a GraphQL operation (inside the outermost braces)."""
    # Strip operation type and name
    stripped = query_str.strip()

    # Handle named operations: query QueryName($var: Type!) { ... }
    for prefix in ("query", "mutation", "subscription"):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :].strip()
            break

    # Skip operation name and variables
    if stripped and stripped[0] != "{":
        # Skip to the first {
        idx = stripped.find("{")
        if idx >= 0:
            stripped = stripped[idx:]

    # Remove outer braces
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped[1:-1].strip()
    return stripped


def validate_selection(
    fields: list[tuple[str, str | None]],
    schema_type: SchemaType,
    schema_types: dict[str, SchemaType],
    path: str,
    method_name: str,
) -> list[ValidationIssue]:
    """Recursively validate a selection set against the schema."""
    issues: list[ValidationIssue] = []

    for field_name, sub_selection in fields:
        field_path = f"{path}.{field_name}"

        # Check if field exists on the type
        if field_name not in schema_type.fields:
            # Check for close matches (typos or renames)
            available = list(schema_type.fields.keys())
            close = [
                f for f in available if _similar(field_name, f)
            ]
            suggestion = ""
            if close:
                suggestion = f" Did you mean: {', '.join(close)}?"

            issues.append(
                ValidationIssue(
                    method_name=method_name,
                    severity="ERROR",
                    message=(
                        f"Field '{field_name}' does not exist on type"
                        f" '{schema_type.name}'.{suggestion}"
                        f" Available fields: {', '.join(sorted(available))}"
                    ),
                    field_path=field_path,
                )
            )
            continue

        schema_field = schema_type.fields[field_name]

        # If there's a sub-selection, validate it recursively
        if sub_selection:
            # Resolve the target type
            target_type_name = schema_field.type_name
            if target_type_name and target_type_name in schema_types:
                sub_fields = _parse_graphql_selection_set(sub_selection)
                sub_issues = validate_selection(
                    sub_fields,
                    schema_types[target_type_name],
                    schema_types,
                    field_path,
                    method_name,
                )
                issues.extend(sub_issues)
            elif target_type_name:
                # Type referenced but not found in schema
                issues.append(
                    ValidationIssue(
                        method_name=method_name,
                        severity="WARNING",
                        message=(
                            f"Type '{target_type_name}' referenced by"
                            f" '{field_name}' not found in schema"
                        ),
                        field_path=field_path,
                    )
                )
        elif schema_field.type_kind == "OBJECT" and schema_field.type_name:
            # Field is an object type but no sub-selection was provided
            issues.append(
                ValidationIssue(
                    method_name=method_name,
                    severity="WARNING",
                    message=(
                        f"Field '{field_name}' is type '{schema_field.type_name}'"
                        f" (OBJECT) but has no sub-selection"
                    ),
                    field_path=field_path,
                )
            )

    return issues


def _similar(a: str, b: str) -> bool:
    """Check if two strings are similar (simple edit distance check)."""
    a_lower = a.lower()
    b_lower = b.lower()
    if a_lower == b_lower:
        return True
    if a_lower in b_lower or b_lower in a_lower:
        return True
    # Simple Levenshtein distance <= 2
    if abs(len(a) - len(b)) > 2:
        return False
    # Count common characters
    common = sum(1 for c in a_lower if c in b_lower)
    return common >= max(len(a), len(b)) - 2


def validate_queries(
    queries: list[ExtractedQuery],
    schema_types: dict[str, SchemaType],
) -> list[ValidationIssue]:
    """Validate all extracted queries against the schema."""
    all_issues: list[ValidationIssue] = []

    # Determine root types
    root_type_map = {
        "query": "Query",
        "mutation": "Mutation",
        "subscription": "Subscription",
    }

    for eq in queries:
        root_type_name = root_type_map.get(eq.operation_type)
        if not root_type_name or root_type_name not in schema_types:
            all_issues.append(
                ValidationIssue(
                    method_name=eq.method_name,
                    severity="WARNING",
                    message=(
                        f"Root type '{root_type_name}' not found in schema"
                        f" for operation type '{eq.operation_type}'"
                    ),
                    field_path=root_type_name or "UNKNOWN",
                )
            )
            continue

        root_type = schema_types[root_type_name]
        body = _extract_body(eq.query_string)
        fields = _parse_graphql_selection_set(body)
        issues = validate_selection(
            fields, root_type, schema_types, root_type_name, eq.method_name
        )
        all_issues.extend(issues)

    return all_issues


# =============================================================================
# Live Method Execution & Response Validation
# =============================================================================


@dataclass
class LiveTestResult:
    """Result of a live method test."""

    method_name: str
    status: str  # PASS, FAIL, SKIP, WARN
    message: str
    response_summary: str = ""


async def run_live_method_tests(client: UnraidClient) -> list[LiveTestResult]:
    """Run every client method and validate responses."""
    results: list[LiveTestResult] = []

    # Query methods that return raw dicts
    raw_methods: list[tuple[str, str]] = [
        ("test_connection", "Connection test"),
        ("get_version", "API version"),
        ("get_system_info", "System info"),
        ("get_registration", "Registration"),
        ("get_vars", "System vars"),
        ("get_owner", "Owner"),
        ("get_flash", "Flash info"),
        ("get_services", "Services"),
        ("get_array_status", "Array status"),
        ("get_array_disks", "Array disks"),
        ("get_shares", "Shares"),
        ("get_containers", "Containers"),
        ("get_docker_networks", "Docker networks"),
        ("get_vms", "VMs"),
        ("get_ups_status", "UPS status"),
        ("get_plugins", "Plugins"),
        ("get_notifications", "Notifications"),
        ("get_parity_history", "Parity history"),
        ("get_log_files", "Log files"),
        ("get_cloud", "Cloud"),
        ("get_connect", "Connect"),
        ("get_remote_access", "Remote access"),
        ("get_system_metrics", "System metrics"),
        ("get_metrics", "Raw metrics"),
    ]

    # Typed methods that return Pydantic models
    typed_methods: list[tuple[str, str]] = [
        ("typed_get_vars", "Typed vars"),
        ("typed_get_registration", "Typed registration"),
        ("typed_get_services", "Typed services"),
        ("typed_get_array", "Typed array"),
        ("typed_get_containers", "Typed containers"),
        ("typed_get_vms", "Typed VMs"),
        ("typed_get_ups_devices", "Typed UPS"),
        ("typed_get_shares", "Typed shares"),
        ("typed_get_flash", "Typed flash"),
        ("typed_get_owner", "Typed owner"),
        ("typed_get_plugins", "Typed plugins"),
        ("typed_get_docker_networks", "Typed networks"),
        ("typed_get_log_files", "Typed log files"),
        ("typed_get_cloud", "Typed cloud"),
        ("typed_get_connect", "Typed connect"),
        ("typed_get_remote_access", "Typed remote access"),
        ("typed_get_me", "Typed user account"),
        ("typed_get_api_keys", "Typed API keys"),
        ("get_notification_overview", "Notification overview"),
    ]

    # v4.30.0 methods
    v430_methods: list[tuple[str, str]] = [
        ("get_container_update_statuses", "Container updates"),
        ("get_ups_configuration", "UPS configuration"),
        ("get_display_settings", "Display settings"),
        ("get_docker_port_conflicts", "Port conflicts"),
    ]

    all_methods = raw_methods + typed_methods + v430_methods

    for method_name, description in all_methods:
        method = getattr(client, method_name, None)
        if method is None:
            results.append(
                LiveTestResult(
                    method_name=method_name,
                    status="SKIP",
                    message=f"Method not found on client",
                )
            )
            continue

        try:
            result = await method()
            summary = _summarize_result(result)
            results.append(
                LiveTestResult(
                    method_name=method_name,
                    status="PASS",
                    message=description,
                    response_summary=summary,
                )
            )
        except Exception as e:
            results.append(
                LiveTestResult(
                    method_name=method_name,
                    status="FAIL",
                    message=f"{type(e).__name__}: {e}",
                )
            )

    return results


def _summarize_result(result: Any) -> str:
    """Create a brief summary of a method's return value."""
    if result is None:
        return "None"
    if isinstance(result, bool):
        return str(result)
    if isinstance(result, dict):
        keys = list(result.keys())[:5]
        return f"dict({len(result)} keys: {', '.join(keys)})"
    if isinstance(result, list):
        return f"list({len(result)} items)"
    type_name = type(result).__name__
    return f"{type_name}"


# =============================================================================
# Schema Diff — Compare Schema Types vs Pydantic Models
# =============================================================================


def compare_models_to_schema(
    schema_types: dict[str, SchemaType],
) -> list[ValidationIssue]:
    """Compare Pydantic models to GraphQL schema types to find drift."""
    import importlib

    models_module = importlib.import_module("unraid_api.models")
    issues: list[ValidationIssue] = []

    # Map Pydantic model names to likely GraphQL type names
    model_to_gql_type: dict[str, list[str]] = {
        "ArrayCapacity": ["ArrayCapacity"],
        "CapacityKilobytes": ["ArrayCapacityKilobytes", "CapacityKilobytes"],
        "ArrayDisk": [
            "UnraidArrayDisk",
            "ArrayDisk",
            "UnraidArrayBootDevice",
        ],
        "UnraidArray": ["UnraidArray"],
        "ParityCheck": [
            "ParityCheck",
            "ParityCheckStatus",
            "UnraidArrayParityCheckStatus",
        ],
        "DockerContainer": ["DockerContainer"],
        "VmDomain": ["VmDomain", "Domain"],
        "Share": ["Share", "UnraidShare"],
        "UPSDevice": ["UPSDevice", "Ups"],
        "UPSBattery": ["UPSBattery", "UpsBattery"],
        "UPSPower": ["UPSPower", "UpsPower"],
        "Vars": ["Vars"],
        "Registration": ["Registration"],
        "Service": ["Service"],
        "Flash": ["Flash"],
        "Owner": ["Owner"],
        "Plugin": ["Plugin"],
    }

    for model_name, possible_gql_types in model_to_gql_type.items():
        model_class = getattr(models_module, model_name, None)
        if model_class is None:
            continue

        # Get Pydantic model fields
        try:
            model_fields = set(model_class.model_fields.keys())
        except AttributeError:
            continue

        # Find matching schema type
        matched_type = None
        for gql_name in possible_gql_types:
            if gql_name in schema_types:
                matched_type = schema_types[gql_name]
                break

        if matched_type is None:
            issues.append(
                ValidationIssue(
                    method_name="model_comparison",
                    severity="INFO",
                    message=(
                        f"Pydantic model '{model_name}' has no matching"
                        f" GraphQL type (tried: {', '.join(possible_gql_types)})"
                    ),
                    field_path=model_name,
                )
            )
            continue

        schema_fields = set(matched_type.fields.keys())

        # Fields in model but not in schema (may cause query failures)
        model_only = model_fields - schema_fields
        for f in sorted(model_only):
            # Skip computed properties and internal fields
            if f.startswith("_"):
                continue
            issues.append(
                ValidationIssue(
                    method_name="model_comparison",
                    severity="INFO",
                    message=(
                        f"Pydantic field '{model_name}.{f}' not found in"
                        f" GraphQL type '{matched_type.name}'"
                        f" (may be computed/aliased)"
                    ),
                    field_path=f"{model_name}.{f}",
                )
            )

        # Fields in schema but not in model (may be missing data)
        schema_only = schema_fields - model_fields
        for f in sorted(schema_only):
            issues.append(
                ValidationIssue(
                    method_name="model_comparison",
                    severity="INFO",
                    message=(
                        f"GraphQL field '{matched_type.name}.{f}' not in"
                        f" Pydantic model '{model_name}'"
                        f" (not queried by client)"
                    ),
                    field_path=f"{matched_type.name}.{f}",
                )
            )

    return issues


# =============================================================================
# Report Formatting
# =============================================================================


def print_schema_summary(schema_types: dict[str, SchemaType]) -> None:
    """Print a summary of the introspected schema."""
    print("\n" + "=" * 70)
    print("GRAPHQL SCHEMA SUMMARY")
    print("=" * 70)

    # Count by kind
    kinds: dict[str, int] = {}
    for t in schema_types.values():
        kinds[t.kind] = kinds.get(t.kind, 0) + 1

    for kind, count in sorted(kinds.items()):
        print(f"  {kind}: {count} types")

    # Show key types
    key_types = [
        "Query",
        "Mutation",
        "Subscription",
        "UnraidArray",
        "ArrayCapacity",
        "UnraidArrayDisk",
        "DockerContainer",
        "Share",
    ]
    print(f"\n{'─' * 70}")
    print("KEY TYPES:")
    for type_name in key_types:
        if type_name in schema_types:
            t = schema_types[type_name]
            fields = sorted(t.fields.keys())
            print(f"\n  {type_name} ({len(fields)} fields):")
            # Print fields in columns
            for j in range(0, len(fields), 4):
                row = fields[j : j + 4]
                print(f"    {', '.join(row)}")


def print_validation_report(
    query_issues: list[ValidationIssue],
    model_issues: list[ValidationIssue],
    live_results: list[LiveTestResult] | None,
    github_diff: list[SchemaDiffIssue] | None = None,
    github_query_issues: list[ValidationIssue] | None = None,
) -> int:
    """Print the full validation report. Returns exit code."""
    exit_code = 0

    # Official GitHub schema comparison
    if github_diff is not None:
        print("\n" + "=" * 70)
        print("OFFICIAL GITHUB SCHEMA ↔ LIVE SERVER COMPARISON")
        print("=" * 70)

        diff_errors = [d for d in github_diff if d.severity == "ERROR"]
        diff_warnings = [d for d in github_diff if d.severity == "WARNING"]
        diff_info = [d for d in github_diff if d.severity == "INFO"]

        if not diff_errors and not diff_warnings and not diff_info:
            print("\n  ✅ Official and live schemas are in sync!")
        else:
            if diff_errors:
                exit_code = 1
                print(f"\n  ❌ {len(diff_errors)} ERROR(s):")
                for d in diff_errors:
                    print(f"    • {d.message}")
            if diff_warnings:
                print(f"\n  ⚠️  {len(diff_warnings)} WARNING(s) — official↔live drift:")
                for d in diff_warnings:
                    print(f"    • {d.message}")
            if diff_info:
                print(f"\n  ℹ️  {len(diff_info)} info note(s):")
                for d in diff_info:
                    print(f"    • {d.message}")

    # Client queries vs official schema
    if github_query_issues is not None:
        print("\n" + "=" * 70)
        print("CLIENT QUERIES ↔ OFFICIAL GITHUB SCHEMA VALIDATION")
        print("=" * 70)

        gh_errors = [i for i in github_query_issues if i.severity == "ERROR"]
        gh_warnings = [i for i in github_query_issues if i.severity == "WARNING"]

        if not gh_errors and not gh_warnings:
            print("\n  ✅ All client queries are valid against the official schema!")
        else:
            if gh_errors:
                exit_code = 1
                print(f"\n  ❌ {len(gh_errors)} ERROR(s) — fields NOT in official schema:")
                for issue in gh_errors:
                    print(f"\n    [{issue.method_name}] {issue.field_path}")
                    print(f"      {issue.message}")
            if gh_warnings:
                print(f"\n  ⚠️  {len(gh_warnings)} WARNING(s):")
                for issue in gh_warnings:
                    print(f"\n    [{issue.method_name}] {issue.field_path}")
                    print(f"      {issue.message}")

    # Query validation (live server)
    print("\n" + "=" * 70)
    print("CLIENT QUERIES ↔ LIVE SERVER SCHEMA VALIDATION")
    print("=" * 70)

    errors = [i for i in query_issues if i.severity == "ERROR"]
    warnings = [i for i in query_issues if i.severity == "WARNING"]

    if not errors and not warnings:
        print("\n  ✅ All query fields match the server schema!")
    else:
        if errors:
            exit_code = 1
            print(f"\n  ❌ {len(errors)} ERROR(s) — fields NOT in schema:")
            for issue in errors:
                print(f"\n    [{issue.method_name}] {issue.field_path}")
                print(f"      {issue.message}")

        if warnings:
            print(f"\n  ⚠️  {len(warnings)} WARNING(s):")
            for issue in warnings:
                print(f"\n    [{issue.method_name}] {issue.field_path}")
                print(f"      {issue.message}")

    # Model comparison
    print("\n" + "=" * 70)
    print("PYDANTIC MODEL ↔ SCHEMA COMPARISON")
    print("=" * 70)

    info_issues = [i for i in model_issues if i.severity == "INFO"]
    model_errors = [i for i in model_issues if i.severity == "ERROR"]

    if model_errors:
        exit_code = 1
        print(f"\n  ❌ {len(model_errors)} ERROR(s):")
        for issue in model_errors:
            print(f"    {issue.message}")

    if info_issues:
        print(f"\n  ℹ️  {len(info_issues)} info note(s):")
        # Group by model name
        by_model: dict[str, list[str]] = {}
        for issue in info_issues:
            model = issue.field_path.split(".")[0]
            by_model.setdefault(model, []).append(issue.message)
        for model, msgs in sorted(by_model.items()):
            print(f"\n    {model}:")
            for msg in msgs:
                print(f"      • {msg}")
    else:
        print("\n  ✅ Models align with schema types!")

    # Live method results
    if live_results is not None:
        print("\n" + "=" * 70)
        print("LIVE METHOD EXECUTION")
        print("=" * 70)

        passed = sum(1 for r in live_results if r.status == "PASS")
        failed = sum(1 for r in live_results if r.status == "FAIL")
        skipped = sum(1 for r in live_results if r.status == "SKIP")

        for r in live_results:
            icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️", "WARN": "⚠️"}.get(
                r.status, "?"
            )
            line = f"  {icon} {r.method_name}"
            if r.response_summary:
                line += f" → {r.response_summary}"
            if r.status == "FAIL":
                line += f"\n       {r.message}"
            print(line)

        print(f"\n  Results: {passed} passed, {failed} failed, {skipped} skipped")
        if failed:
            exit_code = 1

    # Overall result
    print("\n" + "=" * 70)
    if exit_code == 0:
        print("✅ OVERALL: ALL VALIDATIONS PASSED")
    else:
        print("❌ OVERALL: ISSUES FOUND — See errors above")
    print("=" * 70)

    return exit_code


# =============================================================================
# Main
# =============================================================================


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unraid API ↔ GraphQL Schema Cross-Check Validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            This tool validates that the unraid-api client's GraphQL queries,
            mutations, and subscriptions match BOTH the actual Unraid server
            schema AND the official schema from github.com/unraid/api.

            Three-way cross-check:
              Official GitHub Schema ↔ Live Server ↔ Our Client

            It catches issues like ha-unraid#196 where field renames or nesting
            changes break the client at runtime.

            examples:
              %(prog)s                  # Full validation (GitHub + live + schema)
              %(prog)s --schema-only    # Validate queries against schema only
              %(prog)s --live-only      # Run live method tests only
              %(prog)s --github-only    # Only check against GitHub official schema
              %(prog)s --no-github      # Skip GitHub schema check
              %(prog)s --dump-schema    # Dump full introspected schema to JSON
              %(prog)s --github-branch dev  # Use a specific branch
        """),
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Only run schema introspection and field validation",
    )
    parser.add_argument(
        "--live-only",
        action="store_true",
        help="Only run live method execution tests",
    )
    parser.add_argument(
        "--github-only",
        action="store_true",
        help="Only fetch and validate against the official GitHub schema (no live server needed)",
    )
    parser.add_argument(
        "--no-github",
        action="store_true",
        help="Skip the official GitHub schema cross-check",
    )
    parser.add_argument(
        "--github-branch",
        type=str,
        default=None,
        help="Branch of unraid/api to fetch schema from (default: main)",
    )
    parser.add_argument(
        "--dump-schema",
        action="store_true",
        help="Dump the introspected schema to schema-dump.json",
    )
    args = parser.parse_args()

    # Find client source
    client_path = (
        Path(__file__).resolve().parent.parent / "src" / "unraid_api" / "client.py"
    )
    if not client_path.exists():
        print(f"ERROR: Client source not found at {client_path}")
        return 1

    # === Phase 0: Fetch official GitHub schema (unless disabled) ===
    official_types: dict[str, SchemaType] | None = None
    github_diff: list[SchemaDiffIssue] | None = None
    github_query_issues: list[ValidationIssue] | None = None

    if not args.no_github:
        print("\n→ Fetching official schema from github.com/unraid/api...")
        try:
            sdl = fetch_official_schema_sdl(branch=args.github_branch)
            official_types = parse_sdl_to_schema_types(sdl)
            branch_label = args.github_branch or "main"
            print(f"  Parsed {len(official_types)} types from official schema ({branch_label})")

            # Count by kind for summary
            kinds: dict[str, int] = {}
            for t in official_types.values():
                kinds[t.kind] = kinds.get(t.kind, 0) + 1
            for kind, count in sorted(kinds.items()):
                print(f"    {kind}: {count}")
        except Exception as e:
            print(f"  WARNING: Could not fetch official schema: {e}")
            print("  Continuing without official schema check...")
            official_types = None

    # If --github-only, validate client queries against official schema only
    if args.github_only:
        if official_types is None:
            print("ERROR: Could not fetch official schema for --github-only mode")
            return 1

        print("\n→ Extracting GraphQL operations from client source...")
        queries = extract_queries_from_source(str(client_path))
        seen: set[str] = set()
        unique_queries: list[ExtractedQuery] = []
        for q in queries:
            key = q.query_string.strip()
            if key not in seen:
                seen.add(key)
                unique_queries.append(q)
        print(f"  Found {len(unique_queries)} unique operations")

        print("\n→ Validating client queries against official GitHub schema...")
        github_query_issues = validate_queries(unique_queries, official_types)

        print("\n→ Comparing Pydantic models to official schema types...")
        model_issues = compare_models_to_schema(official_types)

        return print_validation_report(
            query_issues=[],
            model_issues=model_issues,
            live_results=None,
            github_diff=None,
            github_query_issues=github_query_issues,
        )

    # === Phases requiring live server ===
    host, api_key = load_env()
    print(f"\nHost: {_sanitize_host(host)}")
    print(f"API Key: {'*' * 8}...{'*' * 4} (loaded)")

    async with UnraidClient(host, api_key, verify_ssl=False) as client:
        # Get server version for context
        try:
            ver = await client.get_version()
            print(f"Server: Unraid {ver.unraid}, API {ver.api}")
        except Exception as e:
            print(f"WARNING: Could not get server version: {e}")

        # Step 1: Introspect live schema
        print("\n→ Introspecting live GraphQL schema...")
        schema_types = await introspect_schema(client)
        print(f"  Found {len(schema_types)} types")

        if args.dump_schema:
            dump_path = Path(__file__).resolve().parent / "schema-dump.json"
            dump_data = {}
            for type_name, st in sorted(schema_types.items()):
                dump_data[type_name] = {
                    "kind": st.kind,
                    "fields": {
                        fn: {
                            "type": sf.type_name,
                            "kind": sf.type_kind,
                            "is_list": sf.is_list,
                            "is_non_null": sf.is_non_null,
                            "args": sf.args,
                        }
                        for fn, sf in sorted(st.fields.items())
                    },
                    "enum_values": st.enum_values,
                }
            dump_path.write_text(json.dumps(dump_data, indent=2))
            print(f"  Schema dumped to {dump_path}")

        print_schema_summary(schema_types)

        # Step 2: Compare official schema vs live server
        if official_types is not None:
            print("\n→ Comparing official GitHub schema ↔ live server...")
            github_diff = compare_official_vs_live(official_types, schema_types)
            warnings = sum(1 for d in github_diff if d.severity == "WARNING")
            info = sum(1 for d in github_diff if d.severity == "INFO")
            print(f"  Found {warnings} warnings, {info} info notes")

        query_issues: list[ValidationIssue] = []
        model_issues: list[ValidationIssue] = []
        live_results: list[LiveTestResult] | None = None

        if not args.live_only:
            # Step 3: Extract and validate queries
            print("\n→ Extracting GraphQL operations from client source...")
            queries = extract_queries_from_source(str(client_path))
            print(f"  Found {len(queries)} operations")

            # Deduplicate by query string
            seen: set[str] = set()
            unique_queries: list[ExtractedQuery] = []
            for q in queries:
                key = q.query_string.strip()
                if key not in seen:
                    seen.add(key)
                    unique_queries.append(q)
            print(f"  {len(unique_queries)} unique operations")

            print("\n→ Validating query fields against live schema...")
            query_issues = validate_queries(unique_queries, schema_types)

            # Also validate against official schema
            if official_types is not None:
                print("\n→ Validating query fields against official GitHub schema...")
                github_query_issues = validate_queries(unique_queries, official_types)

            print("\n→ Comparing Pydantic models to schema types...")
            model_issues = compare_models_to_schema(schema_types)

        if not args.schema_only:
            # Step 4: Run live method tests
            print("\n→ Running live method tests...")
            live_results = await run_live_method_tests(client)

    return print_validation_report(
        query_issues, model_issues, live_results, github_diff, github_query_issues
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
