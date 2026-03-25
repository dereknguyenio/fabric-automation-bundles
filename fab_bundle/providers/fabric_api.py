"""
Fabric REST API provider — wraps Fabric APIs for bundle operations.

Handles authentication, workspace operations, and item CRUD.
Uses azure-identity for authentication.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from azure.identity import (
    ClientSecretCredential,
    DefaultAzureCredential,
    InteractiveBrowserCredential,
)


FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

# Fabric item type mappings
ITEM_TYPE_MAP = {
    "lakehouses": "Lakehouse",
    "notebooks": "Notebook",
    "pipelines": "DataPipeline",
    "warehouses": "Warehouse",
    "semantic_models": "SemanticModel",
    "reports": "Report",
    "data_agents": "DataAgent",
    "environments": "SparkEnvironment",
    "eventhouses": "Eventhouse",
    "eventstreams": "Eventstream",
    "ml_models": "MLModel",
    "ml_experiments": "MLExperiment",
}


@dataclass
class FabricAuth:
    """Authentication configuration for Fabric API."""
    client_id: str | None = None
    client_secret: str | None = None
    tenant_id: str | None = None
    use_browser: bool = False

    def get_credential(self):
        """Get the appropriate Azure credential."""
        if self.client_id and self.client_secret and self.tenant_id:
            return ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
        elif self.use_browser:
            return InteractiveBrowserCredential()
        else:
            return DefaultAzureCredential()

    def get_token(self) -> str:
        """Get an access token for the Fabric API."""
        credential = self.get_credential()
        token = credential.get_token(FABRIC_SCOPE)
        return token.token


@dataclass
class FabricApiError(Exception):
    """Raised when a Fabric API call fails."""
    status_code: int
    message: str
    request_id: str | None = None

    def __str__(self) -> str:
        msg = f"Fabric API Error ({self.status_code}): {self.message}"
        if self.request_id:
            msg += f" [request_id={self.request_id}]"
        return msg


class FabricClient:
    """
    Client for the Microsoft Fabric REST API.

    Provides workspace and item CRUD operations needed for bundle deployment.
    """

    def __init__(self, auth: FabricAuth | None = None):
        self.auth = auth or FabricAuth()
        self._token: str | None = None
        self._session = requests.Session()

    @property
    def _headers(self) -> dict[str, str]:
        if not self._token:
            self._token = self.auth.get_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        retry_count: int = 3,
    ) -> dict[str, Any] | list[Any] | None:
        """Make an authenticated API request with retry logic."""
        url = f"{FABRIC_API_BASE}{path}"

        for attempt in range(retry_count):
            try:
                resp = self._session.request(
                    method=method,
                    url=url,
                    headers=self._headers,
                    json=data,
                    params=params,
                    timeout=60,
                )

                if resp.status_code == 401:
                    # Token expired — refresh
                    self._token = self.auth.get_token()
                    continue

                if resp.status_code == 429:
                    # Rate limited — back off
                    retry_after = int(resp.headers.get("Retry-After", 10))
                    time.sleep(retry_after)
                    continue

                if resp.status_code >= 400:
                    error_body = resp.json() if resp.text else {}
                    raise FabricApiError(
                        status_code=resp.status_code,
                        message=error_body.get("error", {}).get("message", resp.text),
                        request_id=resp.headers.get("x-ms-request-id"),
                    )

                if resp.status_code == 204:
                    return None

                if resp.status_code == 202:
                    # Long-running operation — return location header
                    return {"operation_url": resp.headers.get("Location"), "retry_after": resp.headers.get("Retry-After", "5")}

                return resp.json() if resp.text else None

            except requests.RequestException as e:
                if attempt == retry_count - 1:
                    raise FabricApiError(status_code=0, message=str(e))
                time.sleep(2 ** attempt)

        raise FabricApiError(status_code=0, message="Max retries exceeded")

    def _wait_for_operation(self, operation_url: str, timeout: int = 300) -> dict[str, Any] | None:
        """Poll a long-running operation until completion."""
        start = time.time()
        while time.time() - start < timeout:
            resp = self._session.get(operation_url, headers=self._headers, timeout=60)
            if resp.status_code == 200:
                result = resp.json()
                status = result.get("status", "").lower()
                if status in ("succeeded", "completed"):
                    return result
                elif status in ("failed", "cancelled"):
                    raise FabricApiError(
                        status_code=resp.status_code,
                        message=f"Operation {status}: {result.get('error', {}).get('message', 'Unknown error')}",
                    )
            time.sleep(5)
        raise FabricApiError(status_code=0, message=f"Operation timed out after {timeout}s")

    # -----------------------------------------------------------------------
    # Workspace operations
    # -----------------------------------------------------------------------

    def list_workspaces(self) -> list[dict[str, Any]]:
        """List all accessible workspaces."""
        result = self._request("GET", "/workspaces")
        return result.get("value", []) if result else []

    def get_workspace(self, workspace_id: str) -> dict[str, Any]:
        """Get workspace details by ID."""
        return self._request("GET", f"/workspaces/{workspace_id}") or {}

    def find_workspace(self, name: str) -> dict[str, Any] | None:
        """Find a workspace by name."""
        workspaces = self.list_workspaces()
        for ws in workspaces:
            if ws.get("displayName", "").lower() == name.lower():
                return ws
        return None

    def create_workspace(self, name: str, capacity_id: str | None = None, description: str | None = None) -> dict[str, Any]:
        """Create a new workspace."""
        body: dict[str, Any] = {"displayName": name}
        if capacity_id:
            body["capacityId"] = capacity_id
        if description:
            body["description"] = description
        return self._request("POST", "/workspaces", data=body) or {}

    def assign_capacity(self, workspace_id: str, capacity_id: str) -> None:
        """Assign a capacity to a workspace."""
        self._request("POST", f"/workspaces/{workspace_id}/assignToCapacity", data={"capacityId": capacity_id})

    # -----------------------------------------------------------------------
    # Item operations
    # -----------------------------------------------------------------------

    def list_items(self, workspace_id: str, item_type: str | None = None) -> list[dict[str, Any]]:
        """List items in a workspace, optionally filtered by type."""
        params = {}
        if item_type:
            params["type"] = item_type
        result = self._request("GET", f"/workspaces/{workspace_id}/items", params=params)
        return result.get("value", []) if result else []

    def get_item(self, workspace_id: str, item_id: str) -> dict[str, Any]:
        """Get item details."""
        return self._request("GET", f"/workspaces/{workspace_id}/items/{item_id}") or {}

    def create_item(
        self,
        workspace_id: str,
        display_name: str,
        item_type: str,
        definition: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new item in a workspace."""
        body: dict[str, Any] = {
            "displayName": display_name,
            "type": item_type,
        }
        if description:
            body["description"] = description
        if definition:
            body["definition"] = definition
        return self._request("POST", f"/workspaces/{workspace_id}/items", data=body) or {}

    def update_item(
        self,
        workspace_id: str,
        item_id: str,
        display_name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update item metadata."""
        body: dict[str, Any] = {}
        if display_name:
            body["displayName"] = display_name
        if description:
            body["description"] = description
        return self._request("PATCH", f"/workspaces/{workspace_id}/items/{item_id}", data=body) or {}

    def update_item_definition(
        self,
        workspace_id: str,
        item_id: str,
        definition: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update item definition (content)."""
        result = self._request(
            "POST",
            f"/workspaces/{workspace_id}/items/{item_id}/updateDefinition",
            data={"definition": definition},
        )
        # May return 202 for long-running
        if result and "operation_url" in result:
            return self._wait_for_operation(result["operation_url"])
        return result

    def delete_item(self, workspace_id: str, item_id: str) -> None:
        """Delete an item from a workspace."""
        self._request("DELETE", f"/workspaces/{workspace_id}/items/{item_id}")

    def get_item_definition(self, workspace_id: str, item_id: str) -> dict[str, Any]:
        """Get the full definition of an item."""
        result = self._request("POST", f"/workspaces/{workspace_id}/items/{item_id}/getDefinition")
        if result and "operation_url" in result:
            return self._wait_for_operation(result["operation_url"]) or {}
        return result or {}

    # -----------------------------------------------------------------------
    # Workspace role assignments
    # -----------------------------------------------------------------------

    def list_workspace_role_assignments(self, workspace_id: str) -> list[dict[str, Any]]:
        """List role assignments for a workspace."""
        result = self._request("GET", f"/workspaces/{workspace_id}/roleAssignments")
        return result.get("value", []) if result else []

    def add_workspace_role_assignment(
        self,
        workspace_id: str,
        principal_id: str,
        principal_type: str,
        role: str,
    ) -> dict[str, Any]:
        """Add a role assignment to a workspace."""
        body = {
            "principal": {"id": principal_id, "type": principal_type},
            "role": role,
        }
        return self._request("POST", f"/workspaces/{workspace_id}/roleAssignments", data=body) or {}

    # -----------------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------------

    def get_workspace_items_map(self, workspace_id: str) -> dict[str, dict[str, Any]]:
        """
        Get all items in a workspace as a map of display_name -> item_info.

        This is used by the planner to diff against the bundle definition.
        """
        items = self.list_items(workspace_id)
        result: dict[str, dict[str, Any]] = {}
        for item in items:
            name = item.get("displayName", "")
            result[name] = {
                "id": item.get("id"),
                "type": item.get("type"),
                "description": item.get("description"),
            }
        return result
