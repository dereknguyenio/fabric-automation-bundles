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
    "kql_databases": "KQLDatabase",
    "kql_dashboards": "KQLDashboard",
    "kql_querysets": "KQLQueryset",
    "dataflows": "Dataflow",
    "graphql_apis": "GraphQLApi",
    "spark_job_definitions": "SparkJobDefinition",
    "sql_databases": "SQLDatabase",
    "mirrored_databases": "MirroredDatabase",
    "copy_jobs": "CopyJob",
    "airflow_jobs": "ApacheAirflowJob",
    "reflex": "Reflex",
    "mounted_data_factories": "MountedDataFactory",
    "user_data_functions": "UserDataFunction",
    "variable_libraries": "VariableLibrary",
    "ontologies": "Ontology",
    "graphs": "Graph",
    "dbt_jobs": "DataBuildToolJob",
    "datamarts": "Datamart",
    "paginated_reports": "PaginatedReport",
    "dashboards": "Dashboard",
    "mirrored_warehouses": "MirroredWarehouse",
    "snowflake_databases": "SnowflakeDatabase",
    "cosmosdb_databases": "CosmosDBDatabase",
    "mirrored_databricks_catalogs": "MirroredAzureDatabricksCatalog",
    "operations_agents": "OperationsAgent",
    "anomaly_detectors": "AnomalyDetector",
    "digital_twin_builders": "DigitalTwinBuilder",
    "digital_twin_builder_flows": "DigitalTwinBuilderFlow",
    "event_schema_sets": "EventSchemaSet",
    "graph_query_sets": "GraphQuerySet",
    "map_items": "Map",
    "graph_models": "GraphModel",
    "hls_cohorts": "HLSCohort",
}

# Item types that are list-only — cannot be created/deleted via API
LIST_ONLY_TYPES = {
    "Datamart", "MirroredWarehouse", "SQLEndpoint", "Dashboard", "PaginatedReport",
}

# Item types that REQUIRE a definition to create (cannot create empty)
DEFINITION_REQUIRED_TYPES = {
    "MountedDataFactory", "MirroredDatabase", "Report", "SemanticModel",
}

# Item types where definition upload is not supported
NO_DEFINITION_TYPES = {
    "MLModel", "MLExperiment", "Warehouse",
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
                    # Handle both {error: {message}} and {message} formats
                    msg = (
                        error_body.get("message")
                        or error_body.get("error", {}).get("message")
                        or resp.text
                    )
                    # Check if retriable
                    is_retriable = error_body.get("isRetriable", False)
                    if is_retriable and attempt < retry_count - 1:
                        wait = min(30, 5 * (attempt + 1))
                        time.sleep(wait)
                        continue

                    raise FabricApiError(
                        status_code=resp.status_code,
                        message=msg,
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
        creation_payload: dict[str, Any] | None = None,
        folder_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new item in a workspace.

        Uses type-specific endpoints where required (e.g. /lakehouses, /notebooks).
        Falls back to the generic /items endpoint otherwise.
        """
        # Type-specific endpoints required by certain item types
        TYPE_ENDPOINTS = {
            "Lakehouse": "lakehouses",
            "Notebook": "notebooks",
            "Warehouse": "warehouses",
            "SemanticModel": "semanticModels",
            "Report": "reports",
            "DataPipeline": "dataPipelines",
            "SparkEnvironment": "environments",
            "Eventhouse": "eventhouses",
            "Eventstream": "eventstreams",
            "MLModel": "mlModels",
            "MLExperiment": "mlExperiments",
            "DataAgent": "dataAgents",
            "KQLDatabase": "kqlDatabases",
            "KQLDashboard": "kqlDashboards",
            "KQLQueryset": "kqlQuerysets",
            "SparkJobDefinition": "sparkJobDefinitions",
            "GraphQLApi": "graphqlApis",
            "Reflex": "reflexes",
            "CopyJob": "copyJobs",
            "MountedDataFactory": "mountedDataFactories",
            "SnowflakeDatabase": "snowflakeDatabases",
            "DataBuildToolJob": "dataBuildToolJobs",
            "Ontology": "ontologies",
            "MirroredDatabase": "mirroredDatabases",
            "MirroredAzureDatabricksCatalog": "mirroredAzureDatabricksCatalogs",
            "DigitalTwinBuilder": "digitalTwinBuilders",
            "DigitalTwinBuilderFlow": "digitalTwinBuilderFlows",
            "GraphQuerySet": "graphQuerySets",
            "HLSCohort": "hlsCohorts",
            "Dataflow": "dataflows",
            "VariableLibrary": "variableLibraries",
            "UserDataFunction": "userDataFunctions",
            "ApacheAirflowJob": "apacheAirflowJobs",
            "SQLDatabase": "sqlDatabases",
            "CosmosDBDatabase": "cosmosDBDatabases",
            "OperationsAgent": "operationsAgents",
            "AnomalyDetector": "anomalyDetectors",
            "EventSchemaSet": "eventSchemaSets",
            "Map": "maps",
            "GraphModel": "graphModels",
            "Graph": "graphs",
        }

        body: dict[str, Any] = {"displayName": display_name}
        if description:
            body["description"] = description
        if definition:
            body["definition"] = definition
        if creation_payload:
            body["creationPayload"] = creation_payload
        if folder_id:
            body["folderId"] = folder_id

        endpoint = TYPE_ENDPOINTS.get(item_type)
        if endpoint:
            path = f"/workspaces/{workspace_id}/{endpoint}"
        else:
            body["type"] = item_type
            path = f"/workspaces/{workspace_id}/items"

        return self._request("POST", path, data=body) or {}

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
    # Workspace folders
    # -----------------------------------------------------------------------

    def create_folder(self, workspace_id: str, display_name: str) -> dict[str, Any]:
        """Create a folder in a workspace."""
        return self._request(
            "POST",
            f"/workspaces/{workspace_id}/folders",
            data={"displayName": display_name},
        ) or {}

    def list_folders(self, workspace_id: str) -> list[dict[str, Any]]:
        """List folders in a workspace."""
        result = self._request("GET", f"/workspaces/{workspace_id}/folders")
        return result.get("value", []) if result else []

    # -----------------------------------------------------------------------
    # OneLake shortcuts
    # -----------------------------------------------------------------------

    def create_shortcut(
        self,
        workspace_id: str,
        item_id: str,
        shortcut_name: str,
        path: str,
        target: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a OneLake shortcut in a lakehouse.

        Args:
            workspace_id: Workspace ID
            item_id: Lakehouse item ID
            shortcut_name: Display name of the shortcut
            path: Target path in the lakehouse (e.g., /Tables or /Files)
            target: Shortcut target config with type-specific details
        """
        body = {
            "name": shortcut_name,
            "path": path,
            "target": target,
        }
        return self._request(
            "POST",
            f"/workspaces/{workspace_id}/items/{item_id}/shortcuts",
            data=body,
        ) or {}

    def list_shortcuts(self, workspace_id: str, item_id: str) -> list[dict[str, Any]]:
        """List shortcuts in a lakehouse."""
        result = self._request("GET", f"/workspaces/{workspace_id}/items/{item_id}/shortcuts")
        return result.get("value", []) if result else []

    def delete_shortcut(self, workspace_id: str, item_id: str, shortcut_name: str, shortcut_path: str) -> None:
        """Delete a shortcut from a lakehouse."""
        self._request(
            "DELETE",
            f"/workspaces/{workspace_id}/items/{item_id}/shortcuts/{shortcut_path}/{shortcut_name}",
        )

    # -----------------------------------------------------------------------
    # OneLake data access roles
    # -----------------------------------------------------------------------

    def update_lakehouse_data_access_roles(
        self,
        workspace_id: str,
        item_id: str,
        roles: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Update OneLake data access roles for an item (lakehouse, warehouse, etc.)."""
        body = {"value": roles}
        return self._request(
            "PUT",
            f"/workspaces/{workspace_id}/items/{item_id}/dataAccessRoles",
            data=body,
        )

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
    # Environment operations
    # -----------------------------------------------------------------------

    def refresh_semantic_model(self, workspace_id: str, item_id: str) -> dict[str, Any] | None:
        """Trigger a semantic model refresh."""
        result = self._request(
            "POST",
            f"/workspaces/{workspace_id}/semanticModels/{item_id}/refresh",
        )
        if result and "operation_url" in result:
            return self._wait_for_operation(result["operation_url"], timeout=600)
        return result

    def publish_environment(self, workspace_id: str, item_id: str) -> dict[str, Any] | None:
        """Publish a Spark environment (installs libraries). Uses GA API with beta=False."""
        url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/environments/{item_id}/staging/publish"
        params = {"beta": "False"}
        resp = self._session.post(url, headers=self._headers, params=params, timeout=60)

        # Fire-and-forget — environment publish can take 5-10 min, don't block
        if resp.status_code in (200, 202):
            return {"status": "publish_triggered"}
        elif resp.status_code >= 400:
            error_msg = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
            raise Exception(f"Environment publish failed: {error_msg}")
        return None

    def update_environment_libraries(
        self,
        workspace_id: str,
        item_id: str,
        libraries: list[str],
    ) -> dict[str, Any] | None:
        """Upload PyPI libraries via environment.yml to the staging area."""
        # Build environment.yml content
        yml_lines = ["name: fabric-env", "dependencies:"]
        for lib in libraries:
            yml_lines.append(f"  - {lib}")
        yml_content = "\n".join(yml_lines).encode("utf-8")

        url = (
            f"{FABRIC_API_BASE}/workspaces/{workspace_id}/environments/{item_id}"
            f"/staging/libraries/importExternalLibraries"
        )
        headers = {
            "Authorization": f"Bearer {self.auth.get_token()}",
            "Content-Type": "application/octet-stream",
        }
        resp = self._session.post(url, headers=headers, data=yml_content, timeout=60)

        if resp.status_code in (200, 202):
            return {"status": "uploaded"}
        elif resp.status_code >= 400:
            error_msg = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
            raise Exception(f"Environment library upload failed: {error_msg}")
        return None

    # -----------------------------------------------------------------------
    # Workspace tagging
    # -----------------------------------------------------------------------

    def update_item_tags(
        self,
        workspace_id: str,
        item_id: str,
        tags: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        """Update tags on a workspace item."""
        return self._request(
            "POST",
            f"/workspaces/{workspace_id}/items/{item_id}/tags",
            data={"tags": tags},
        )

    # -----------------------------------------------------------------------
    # Capacity management (Azure Resource Manager)
    # -----------------------------------------------------------------------

    def resume_capacity(self, subscription_id: str, resource_group: str, capacity_name: str) -> dict[str, Any] | None:
        """Resume a paused Fabric capacity via ARM API."""
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}/providers/Microsoft.Fabric"
            f"/capacities/{capacity_name}/resume?api-version=2023-11-01"
        )
        try:
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
            token = credential.get_token("https://management.azure.com/.default")
            resp = self._session.post(url, headers={"Authorization": f"Bearer {token.token}"}, timeout=60)
            if resp.status_code in (200, 202):
                return {"status": "resuming"}
            return None
        except Exception:
            return None

    def pause_capacity(self, subscription_id: str, resource_group: str, capacity_name: str) -> dict[str, Any] | None:
        """Pause a Fabric capacity via ARM API."""
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}/providers/Microsoft.Fabric"
            f"/capacities/{capacity_name}/suspend?api-version=2023-11-01"
        )
        try:
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
            token = credential.get_token("https://management.azure.com/.default")
            resp = self._session.post(url, headers={"Authorization": f"Bearer {token.token}"}, timeout=60)
            if resp.status_code in (200, 202):
                return {"status": "pausing"}
            return None
        except Exception:
            return None

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

    # -----------------------------------------------------------------------
    # Workspace deletion
    # -----------------------------------------------------------------------

    def delete_workspace(self, workspace_id: str) -> None:
        """Delete a workspace."""
        self._request("DELETE", f"/workspaces/{workspace_id}")

    # -----------------------------------------------------------------------
    # Git integration
    # -----------------------------------------------------------------------

    def connect_workspace_to_git(
        self,
        workspace_id: str,
        provider: str,
        organization: str,
        project: str | None,
        repository: str,
        branch: str = "main",
        directory: str = "/",
    ) -> dict[str, Any] | None:
        """Connect a workspace to a Git repository."""
        git_provider_details: dict[str, Any] = {
            "organizationName": organization,
            "repositoryName": repository,
            "branchName": branch,
            "directoryName": directory,
        }
        if project:
            git_provider_details["projectName"] = project

        body = {
            "gitProviderDetails": git_provider_details,
        }
        return self._request("POST", f"/workspaces/{workspace_id}/git/connect", data=body)

    def initialize_git_connection(self, workspace_id: str) -> dict[str, Any] | None:
        """Initialize a git connection (initial sync)."""
        result = self._request("POST", f"/workspaces/{workspace_id}/git/initializeConnection", data={})
        if result and "operation_url" in result:
            return self._wait_for_operation(result["operation_url"])
        return result

    def get_git_status(self, workspace_id: str) -> dict[str, Any] | None:
        """Get git sync status for a workspace."""
        return self._request("GET", f"/workspaces/{workspace_id}/git/status")

    def disconnect_workspace_from_git(self, workspace_id: str) -> None:
        """Disconnect a workspace from Git."""
        self._request("POST", f"/workspaces/{workspace_id}/git/disconnect")

    # -----------------------------------------------------------------------
    # Connections
    # -----------------------------------------------------------------------

    def list_connections(self) -> list[dict[str, Any]]:
        """List all connections accessible to the user."""
        result = self._request("GET", "/connections")
        return result.get("value", []) if result else []

    def create_connection(
        self,
        display_name: str,
        connection_type: str,
        connectivity_type: str = "ShareableCloud",
        connection_details: dict[str, Any] | None = None,
        credential_details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new connection."""
        body: dict[str, Any] = {
            "displayName": display_name,
            "connectivityType": connectivity_type,
            "connectionDetails": connection_details or {},
        }
        if credential_details:
            body["credentialDetails"] = credential_details
        return self._request("POST", "/connections", data=body) or {}

    def delete_connection(self, connection_id: str) -> None:
        """Delete a connection."""
        self._request("DELETE", f"/connections/{connection_id}")

    # -----------------------------------------------------------------------
    # Job scheduler
    # -----------------------------------------------------------------------

    def run_item_job(
        self,
        workspace_id: str,
        item_id: str,
        job_type: str,
        execution_data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Trigger a job run for an item (notebook, pipeline, etc.)."""
        body: dict[str, Any] = {}
        if execution_data:
            body["executionData"] = execution_data
        result = self._request(
            "POST",
            f"/workspaces/{workspace_id}/items/{item_id}/jobs/instances?jobType={job_type}",
            data=body if body else None,
        )
        return result

    def get_item_job_instance(
        self,
        workspace_id: str,
        item_id: str,
        job_instance_id: str,
    ) -> dict[str, Any]:
        """Get the status of a job instance."""
        return self._request(
            "GET",
            f"/workspaces/{workspace_id}/items/{item_id}/jobs/instances/{job_instance_id}",
        ) or {}

    # -----------------------------------------------------------------------
    # SQL endpoint execution
    # -----------------------------------------------------------------------

    def execute_sql(
        self,
        workspace_id: str,
        warehouse_id: str,
        sql: str,
    ) -> dict[str, Any] | None:
        """Execute a SQL statement against a Warehouse SQL endpoint."""
        return self._request(
            "POST",
            f"/workspaces/{workspace_id}/warehouses/{warehouse_id}/executeQuery",
            data={"query": sql, "maxRows": 1000},
        )

    def execute_lakehouse_sql(
        self,
        workspace_id: str,
        sql_endpoint_id: str,
        sql: str,
    ) -> dict[str, Any] | None:
        """Execute SQL against a lakehouse SQL endpoint."""
        return self._request(
            "POST",
            f"/workspaces/{workspace_id}/sqlEndpoints/{sql_endpoint_id}/executeQuery",
            data={"query": sql, "maxRows": 1000},
        )

    # -----------------------------------------------------------------------
    # Job scheduling
    # -----------------------------------------------------------------------

    def create_item_schedule(
        self,
        workspace_id: str,
        item_id: str,
        schedule_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a schedule for an item."""
        return self._request(
            "POST",
            f"/workspaces/{workspace_id}/items/{item_id}/jobScheduler",
            data=schedule_config,
        ) or {}

    def update_item_schedule(
        self,
        workspace_id: str,
        item_id: str,
        schedule_config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update a schedule for an item."""
        return self._request(
            "PATCH",
            f"/workspaces/{workspace_id}/items/{item_id}/jobScheduler",
            data=schedule_config,
        )

    def get_item_schedule(
        self,
        workspace_id: str,
        item_id: str,
    ) -> dict[str, Any] | None:
        """Get the schedule for an item."""
        return self._request(
            "GET",
            f"/workspaces/{workspace_id}/items/{item_id}/jobScheduler",
        )
