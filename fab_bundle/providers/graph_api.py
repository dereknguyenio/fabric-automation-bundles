"""
Microsoft Graph API client — resolves Entra ID display names to object GUIDs.

Used by the deployer to convert human-readable security role references
(e.g., 'sg-data-engineering') to the GUIDs required by the Fabric API.
"""

from __future__ import annotations

import re
from typing import Any

import requests
from azure.identity import DefaultAzureCredential


GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE
)


def is_guid(value: str) -> bool:
    """Check if a string is already a GUID."""
    return bool(GUID_PATTERN.match(value))


class GraphClient:
    """Client for Microsoft Graph API — resolves Entra ID identities."""

    def __init__(self, credential: Any | None = None):
        self._credential = credential or DefaultAzureCredential()
        self._token: str | None = None
        self._session = requests.Session()
        self._cache: dict[str, str | None] = {}

    def _get_token(self) -> str:
        if not self._token:
            token = self._credential.get_token(GRAPH_SCOPE)
            self._token = token.token
        return self._token

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, params: dict | None = None) -> dict[str, Any] | None:
        url = f"{GRAPH_API_BASE}{path}"
        try:
            resp = self._session.request(method, url, headers=self._headers, params=params, timeout=30)
            if resp.status_code == 401:
                self._token = None
                resp = self._session.request(method, url, headers=self._headers, params=params, timeout=30)
            if resp.status_code >= 400:
                return None
            return resp.json() if resp.text else None
        except requests.RequestException:
            return None

    def resolve_group(self, display_name: str) -> str | None:
        """Resolve a group display name to its object ID."""
        if is_guid(display_name):
            return display_name

        cache_key = f"group:{display_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._request(
            "GET", "/groups",
            params={"$filter": f"displayName eq '{display_name}'", "$select": "id"},
        )
        groups = (result or {}).get("value", [])
        guid = groups[0]["id"] if groups else None
        self._cache[cache_key] = guid
        return guid

    def resolve_user(self, user_principal_name: str) -> str | None:
        """Resolve a UPN or display name to a user object ID."""
        if is_guid(user_principal_name):
            return user_principal_name

        cache_key = f"user:{user_principal_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try as UPN first
        result = self._request("GET", f"/users/{user_principal_name}", params={"$select": "id"})
        if result and "id" in result:
            self._cache[cache_key] = result["id"]
            return result["id"]

        # Try as display name
        result = self._request(
            "GET", "/users",
            params={"$filter": f"displayName eq '{user_principal_name}'", "$select": "id"},
        )
        users = (result or {}).get("value", [])
        guid = users[0]["id"] if users else None
        self._cache[cache_key] = guid
        return guid

    def resolve_service_principal(self, display_name: str) -> str | None:
        """Resolve a service principal display name or app ID to its object ID."""
        if is_guid(display_name):
            return display_name

        cache_key = f"sp:{display_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try by display name
        result = self._request(
            "GET", "/servicePrincipals",
            params={"$filter": f"displayName eq '{display_name}'", "$select": "id"},
        )
        sps = (result or {}).get("value", [])
        if sps:
            self._cache[cache_key] = sps[0]["id"]
            return sps[0]["id"]

        # Try by appId
        result = self._request(
            "GET", "/servicePrincipals",
            params={"$filter": f"appId eq '{display_name}'", "$select": "id"},
        )
        sps = (result or {}).get("value", [])
        guid = sps[0]["id"] if sps else None
        self._cache[cache_key] = guid
        return guid

    def resolve_principal(
        self, value: str, principal_type: str = "Group"
    ) -> str | None:
        """Resolve any principal type to its GUID."""
        resolvers = {
            "Group": self.resolve_group,
            "User": self.resolve_user,
            "ServicePrincipal": self.resolve_service_principal,
        }
        resolver = resolvers.get(principal_type, self.resolve_group)
        return resolver(value)
