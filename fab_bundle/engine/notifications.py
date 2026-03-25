"""Deployment notifications — send alerts to Slack, Teams, etc."""

from __future__ import annotations

from typing import Any

import requests


def send_slack(webhook_url: str, message: str) -> bool:
    """Send a Slack notification."""
    try:
        resp = requests.post(webhook_url, json={"text": message}, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def send_teams(webhook_url: str, message: str) -> bool:
    """Send a Microsoft Teams notification."""
    try:
        card = {
            "@type": "MessageCard",
            "summary": "Fabric Bundle Deployment",
            "text": message,
        }
        resp = requests.post(webhook_url, json=card, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def notify(config: dict[str, Any], context: dict[str, str]) -> None:
    """Send notifications based on config."""
    message = config.get("message", "Deployment completed")
    # Substitute context variables
    for key, value in context.items():
        message = message.replace(f"{{{key}}}", value)

    notify_type = config.get("type", "")
    webhook = config.get("webhook", "")

    if not webhook:
        return

    if notify_type == "slack":
        send_slack(webhook, message)
    elif notify_type == "teams":
        send_teams(webhook, message)
