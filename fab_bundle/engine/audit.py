"""Audit logging — structured deployment action logging."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class AuditLogger:
    """Logs deployment actions to a structured audit file."""

    def __init__(self, project_dir: Path, target: str = "default"):
        self._log_dir = project_dir / ".fab-bundle"
        self._log_file = self._log_dir / "audit.jsonl"
        self._target = target

    def log(
        self,
        action: str,
        resource: str = "",
        resource_type: str = "",
        status: str = "success",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write an audit log entry."""
        self._log_dir.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": action,
            "resource": resource,
            "resource_type": resource_type,
            "target": self._target,
            "status": status,
            "deployer": os.environ.get("USER", "unknown"),
            "ci_run_id": os.environ.get("GITHUB_RUN_ID", os.environ.get("BUILD_BUILDID", "")),
        }
        if details:
            entry["details"] = details

        with open(self._log_file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def get_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        """Read recent audit log entries."""
        if not self._log_file.exists():
            return []
        entries = []
        for line in self._log_file.read_text().strip().split("\n"):
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries[-limit:]
