"""Policy enforcement — validate bundle against configurable rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fab_bundle.models.bundle import BundleDefinition


def enforce_policies(bundle: BundleDefinition, project_dir: Path | None = None) -> list[str]:
    """Run all policy checks. Returns list of violation messages."""
    violations: list[str] = []
    policies = bundle.policies

    if policies.require_description:
        for field_name in type(bundle.resources).model_fields:
            resource_dict = getattr(bundle.resources, field_name)
            if isinstance(resource_dict, dict):
                for key, res in resource_dict.items():
                    if hasattr(res, "description") and not res.description:
                        violations.append(f"Policy: {key} ({field_name}) missing description")

    if policies.naming_convention == "snake_case":
        import re
        snake = re.compile(r'^[a-z][a-z0-9_]*$')
        for key in bundle.resources.all_resource_keys():
            if not snake.match(key):
                violations.append(f"Policy: '{key}' does not match snake_case convention")

    if policies.max_notebook_size_kb and project_dir:
        for key, nb in bundle.resources.notebooks.items():
            nb_path = project_dir / nb.path
            if nb_path.exists():
                size_kb = nb_path.stat().st_size / 1024
                if size_kb > policies.max_notebook_size_kb:
                    violations.append(f"Policy: '{key}' is {size_kb:.0f}KB (max {policies.max_notebook_size_kb}KB)")

    if policies.blocked_libraries:
        for key, env in bundle.resources.environments.items():
            for lib in env.libraries:
                for blocked in policies.blocked_libraries:
                    if lib.startswith(blocked.split("<")[0].split(">")[0].split("=")[0]):
                        violations.append(f"Policy: '{key}' uses blocked library '{lib}'")

    return violations
