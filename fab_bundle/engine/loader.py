"""
Bundle loader — parses fabric.yml (and included files) into a BundleDefinition.

Handles:
  - YAML parsing with variable interpolation
  - Include file merging
  - Jinja2-style variable substitution in string values
"""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from fab_bundle.models.bundle import BundleDefinition


class BundleLoadError(Exception):
    """Raised when a bundle cannot be loaded."""

    def __init__(self, message: str, errors: list[str] | None = None):
        self.errors = errors or []
        super().__init__(message)


def find_bundle_file(start_dir: str | Path | None = None) -> Path:
    """
    Find fabric.yml by walking up from start_dir (or cwd).

    Searches for: fabric.yml, fabric.yaml, .fabric/bundle.yml, .fabric/bundle.yaml
    """
    search_names = ["fabric.yml", "fabric.yaml", ".fabric/bundle.yml", ".fabric/bundle.yaml"]
    current = Path(start_dir) if start_dir else Path.cwd()

    while True:
        for name in search_names:
            candidate = current / name
            if candidate.is_file():
                return candidate

        parent = current.parent
        if parent == current:
            break
        current = parent

    raise BundleLoadError(
        f"No fabric.yml found in '{start_dir or Path.cwd()}' or any parent directory.\n"
        "Run 'fab bundle init' to create one, or specify a path with --file."
    )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge override into base (override wins on conflicts)."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _resolve_includes(data: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    """Process 'include' directives and merge referenced YAML files."""
    includes = data.pop("include", [])
    if not includes:
        return data

    merged = {}
    for pattern in includes:
        include_path = base_dir / pattern
        if include_path.is_file():
            paths = [include_path]
        else:
            paths = sorted(base_dir.glob(pattern))

        if not paths:
            raise BundleLoadError(f"Include pattern '{pattern}' matched no files (from {base_dir})")

        for p in paths:
            with open(p, "r") as f:
                include_data = yaml.safe_load(f) or {}
            merged = _deep_merge(merged, include_data)

    # Base file overrides included files
    return _deep_merge(merged, data)


def _substitute_variables(obj: Any, variables: dict[str, str]) -> Any:
    """
    Recursively substitute ${var.name} and ${variables.name} patterns.

    Supports:
      - ${var.key} — shorthand
      - ${variables.key} — explicit
      - ${bundle.name} — bundle metadata
      - ${resources.type.key} — resource references (left as-is for runtime resolution)
    """
    if isinstance(obj, str):
        def _replace(match: re.Match) -> str:
            expr = match.group(1)
            # Handle var. and variables. prefixes
            for prefix in ("var.", "variables."):
                if expr.startswith(prefix):
                    var_name = expr[len(prefix):]
                    if var_name in variables:
                        return variables[var_name]
                    return match.group(0)  # Leave unresolved
            return match.group(0)

        return re.sub(r"\$\{([^}]+)\}", _replace, obj)

    elif isinstance(obj, dict):
        return {k: _substitute_variables(v, variables) for k, v in obj.items()}

    elif isinstance(obj, list):
        return [_substitute_variables(item, variables) for item in obj]

    return obj


def load_bundle(
    path: str | Path | None = None,
    target: str | None = None,
) -> BundleDefinition:
    """
    Load and validate a bundle definition from a fabric.yml file.

    Args:
        path: Path to fabric.yml. If None, searches upward from cwd.
        target: Target name to resolve variables for.

    Returns:
        Validated BundleDefinition.

    Raises:
        BundleLoadError: If the file cannot be found, parsed, or validated.
    """
    if path:
        bundle_path = Path(path)
        if not bundle_path.is_file():
            raise BundleLoadError(f"Bundle file not found: {bundle_path}")
    else:
        bundle_path = find_bundle_file()

    base_dir = bundle_path.parent

    # Parse YAML
    try:
        with open(bundle_path, "r") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise BundleLoadError(f"Invalid YAML in {bundle_path}: {e}")

    if not raw_data or not isinstance(raw_data, dict):
        raise BundleLoadError(f"Empty or invalid bundle file: {bundle_path}")

    # Process includes
    try:
        data = _resolve_includes(raw_data, base_dir)
    except BundleLoadError:
        raise
    except Exception as e:
        raise BundleLoadError(f"Error processing includes: {e}")

    # First pass: create bundle to extract variable definitions
    try:
        preliminary = BundleDefinition.model_validate(data)
    except ValidationError as e:
        errors = [f"  {err['loc']}: {err['msg']}" for err in e.errors()]
        raise BundleLoadError(
            f"Bundle validation failed ({bundle_path}):\n" + "\n".join(errors),
            errors=errors,
        )

    # Resolve variables for the target
    variables = preliminary.resolve_variables(target)

    # Add implicit variables
    variables["bundle.name"] = preliminary.bundle.name
    variables["bundle.version"] = preliminary.bundle.version

    # Environment variables
    for key, value in os.environ.items():
        variables[f"env.{key}"] = value

    # Second pass: substitute variables and re-validate
    substituted = _substitute_variables(data, variables)

    try:
        bundle = BundleDefinition.model_validate(substituted)
    except ValidationError as e:
        errors = [f"  {err['loc']}: {err['msg']}" for err in e.errors()]
        raise BundleLoadError(
            f"Bundle validation failed after variable substitution ({bundle_path}):\n"
            + "\n".join(errors),
            errors=errors,
        )

    return bundle


def dump_bundle(bundle: BundleDefinition) -> str:
    """Serialize a BundleDefinition back to YAML."""
    data = bundle.model_dump(exclude_none=True, exclude_defaults=False)
    return yaml.dump(data, default_flow_style=False, sort_keys=False, width=120)
