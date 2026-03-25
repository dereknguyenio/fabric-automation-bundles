"""
State management — tracks deployed resources for drift detection and smart planning.

Stores deployment state in .fab-bundle-state.json alongside fabric.yml.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


STATE_FILE_NAME = ".fab-bundle-state.json"
STATE_VERSION = 1


@dataclass
class ResourceState:
    """State of a single deployed resource."""
    item_id: str
    item_type: str
    resource_key: str
    definition_hash: str | None = None
    last_deployed: float = 0.0
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResourceState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DeploymentState:
    """Full deployment state for a bundle + target."""
    version: int = STATE_VERSION
    bundle_name: str = ""
    bundle_version: str = ""
    target_name: str = ""
    workspace_id: str = ""
    workspace_name: str = ""
    last_deployed: float = 0.0
    resources: dict[str, ResourceState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "bundle_name": self.bundle_name,
            "bundle_version": self.bundle_version,
            "target_name": self.target_name,
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "last_deployed": self.last_deployed,
            "resources": {k: v.to_dict() for k, v in self.resources.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeploymentState":
        resources = {}
        for key, res_data in data.get("resources", {}).items():
            resources[key] = ResourceState.from_dict(res_data)
        return cls(
            version=data.get("version", STATE_VERSION),
            bundle_name=data.get("bundle_name", ""),
            bundle_version=data.get("bundle_version", ""),
            target_name=data.get("target_name", ""),
            workspace_id=data.get("workspace_id", ""),
            workspace_name=data.get("workspace_name", ""),
            last_deployed=data.get("last_deployed", 0.0),
            resources=resources,
        )


class StateManager:
    """Manages deployment state persistence and drift detection.

    Supports pluggable backends:
    - local: file-based in .fab-bundle/ (default)
    - azureblob: Azure Blob Storage (for team/CI state sharing)
    - adls: Azure Data Lake Storage Gen2

    Configure in fabric.yml:
        state:
          backend: azureblob
          config:
            account_name: mystorageaccount
            container_name: fab-bundle-state
    """

    def __init__(self, project_dir: Path, target_name: str = "default", backend_type: str = "local", backend_config: dict[str, str] | None = None):
        self.project_dir = project_dir
        self.target_name = target_name
        self._state_dir = project_dir / ".fab-bundle"
        self._state_file = self._state_dir / f"state-{target_name}.json"

        # Initialize backend
        from fab_bundle.engine.state_backend import create_backend
        self._backend = create_backend(backend_type, backend_config, project_dir)
        self._state_key = f"state-{target_name}"
        self._lock_key = f"lock-{target_name}"

    def load(self) -> DeploymentState:
        """Load state from backend. Returns empty state if none exists."""
        data = self._backend.read(self._state_key)
        if data:
            return DeploymentState.from_dict(data)
        # Fallback: try local file (migration from old format)
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                return DeploymentState.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                pass
        return DeploymentState(target_name=self.target_name)

    def save(self, state: DeploymentState) -> None:
        """Persist state to backend."""
        self._backend.write(self._state_key, state.to_dict())
        # Also write locally for backwards compatibility
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(
            json.dumps(state.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        gitignore = self._state_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("# Deployment state — machine-specific, do not commit\n*\n")

    def record_deployment(
        self,
        bundle_name: str,
        bundle_version: str,
        workspace_id: str,
        workspace_name: str,
        deployed_items: dict[str, dict[str, Any]],
    ) -> DeploymentState:
        """Record a successful deployment."""
        state = self.load()
        state.bundle_name = bundle_name
        state.bundle_version = bundle_version
        state.workspace_id = workspace_id
        state.workspace_name = workspace_name
        state.last_deployed = time.time()
        state.target_name = self.target_name

        for key, info in deployed_items.items():
            state.resources[key] = ResourceState(
                item_id=info.get("id", ""),
                item_type=info.get("type", ""),
                resource_key=key,
                definition_hash=info.get("definition_hash"),
                last_deployed=time.time(),
                properties=info.get("properties", {}),
            )

        self.save(state)
        self.record_history(state)
        return state

    def remove_resource(self, resource_key: str) -> None:
        """Remove a resource from state (after deletion)."""
        state = self.load()
        state.resources.pop(resource_key, None)
        self.save(state)

    def acquire_lock(self, deployer_id: str = "", timeout_minutes: int = 30) -> bool:
        """Acquire a deployment lock. Uses backend for distributed locking."""
        import socket
        import os
        owner = deployer_id or f"{os.environ.get('USER', 'unknown')}@{socket.gethostname()}"
        ci_run = os.environ.get("GITHUB_RUN_ID", os.environ.get("BUILD_BUILDID", ""))
        if ci_run:
            owner = f"{owner} (CI: {ci_run})"
        return self._backend.acquire_lock(self._lock_key, owner, timeout_minutes * 60)

    def release_lock(self) -> None:
        """Release the deployment lock."""
        self._backend.release_lock(self._lock_key)

    def get_lock_info(self) -> dict[str, Any] | None:
        """Get info about the current lock, or None if unlocked."""
        return self._backend.get_lock_info(self._lock_key)

    def detect_drift(
        self,
        live_items: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        """
        Compare state against live workspace items.

        Returns dict of resource_key -> drift_type where drift_type is one of:
          - 'added': exists in workspace but not in state
          - 'removed': exists in state but not in workspace
          - 'modified': exists in both but properties differ
        """
        state = self.load()
        drift: dict[str, str] = {}

        state_keys = set(state.resources.keys())
        live_keys = set(live_items.keys())

        for key in live_keys - state_keys:
            drift[key] = "added"

        for key in state_keys - live_keys:
            drift[key] = "removed"

        for key in state_keys & live_keys:
            state_res = state.resources[key]
            live_res = live_items[key]
            if state_res.item_id != live_res.get("id", ""):
                drift[key] = "modified"

        return drift


    def record_history(self, state: DeploymentState, summary: str = "") -> None:
        """Record a deployment in the history log."""
        history_dir = self._state_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)

        entry = {
            "deploy_id": f"{int(state.last_deployed)}",
            "timestamp": state.last_deployed,
            "bundle_name": state.bundle_name,
            "bundle_version": state.bundle_version,
            "target": state.target_name,
            "workspace_id": state.workspace_id,
            "resource_count": len(state.resources),
            "summary": summary,
            "resources": {k: {"item_id": v.item_id, "type": v.item_type} for k, v in state.resources.items()},
        }

        filename = f"{int(state.last_deployed)}-{state.target_name}.json"
        (history_dir / filename).write_text(json.dumps(entry, indent=2, default=str))

    def list_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """List deployment history entries, most recent first."""
        history_dir = self._state_dir / "history"
        if not history_dir.exists():
            return []

        entries = []
        for f in sorted(history_dir.glob("*.json"), reverse=True)[:limit]:
            try:
                entries.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, KeyError):
                continue
        return entries

    def get_history_entry(self, deploy_id: str) -> dict[str, Any] | None:
        """Get a specific deployment history entry."""
        history_dir = self._state_dir / "history"
        if not history_dir.exists():
            return None
        for f in history_dir.glob(f"{deploy_id}*.json"):
            try:
                return json.loads(f.read_text())
            except (json.JSONDecodeError, KeyError):
                continue
        return None


def compute_definition_hash(definition: dict[str, Any] | None) -> str | None:
    """Compute a hash of an item definition for change detection."""
    if not definition:
        return None
    canonical = json.dumps(definition, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
