"""Deployment metrics — track deploy performance and outcomes."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class DeploymentMetrics:
    """Metrics for a single deployment."""
    start_time: float = 0.0
    end_time: float = 0.0
    duration_seconds: float = 0.0
    target: str = ""
    items_created: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    items_failed: int = 0
    items_skipped: int = 0
    api_calls: int = 0
    success: bool = True

    def finalize(self) -> None:
        self.end_time = time.time()
        self.duration_seconds = round(self.end_time - self.start_time, 2)


class MetricsCollector:
    """Collects and persists deployment metrics."""

    def __init__(self, project_dir: Path):
        self._metrics_file = project_dir / ".fab-bundle" / "metrics.json"

    def save(self, metrics: DeploymentMetrics) -> None:
        self._metrics_file.parent.mkdir(parents=True, exist_ok=True)
        history = self.load_all()
        history.append(asdict(metrics))
        # Keep last 100 entries
        history = history[-100:]
        self._metrics_file.write_text(json.dumps(history, indent=2, default=str))

    def load_all(self) -> list[dict[str, Any]]:
        if not self._metrics_file.exists():
            return []
        try:
            return json.loads(self._metrics_file.read_text())
        except (json.JSONDecodeError, KeyError):
            return []

    def summary(self) -> dict[str, Any]:
        """Get aggregate metrics summary."""
        entries = self.load_all()
        if not entries:
            return {"total_deploys": 0}

        successes = [e for e in entries if e.get("success")]
        failures = [e for e in entries if not e.get("success")]
        durations = [e.get("duration_seconds", 0) for e in successes]

        return {
            "total_deploys": len(entries),
            "successes": len(successes),
            "failures": len(failures),
            "success_rate": f"{len(successes)/len(entries)*100:.0f}%" if entries else "N/A",
            "avg_duration": f"{sum(durations)/len(durations):.1f}s" if durations else "N/A",
            "total_items_created": sum(e.get("items_created", 0) for e in entries),
            "total_items_updated": sum(e.get("items_updated", 0) for e in entries),
        }
