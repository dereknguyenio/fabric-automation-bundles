"""
Secrets management — resolve secrets from Azure KeyVault or environment variables.

Supports:
  - Environment variables: ${secret.ENV_VAR_NAME}
  - Azure KeyVault: ${keyvault.vault-name.secret-name}
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any


SECRET_PATTERN = re.compile(r"\$\{secret\.([^}]+)\}")
KEYVAULT_PATTERN = re.compile(r"\$\{keyvault\.([^.]+)\.([^}]+)\}")


@dataclass
class SecretReference:
    """A reference to a secret value."""
    source: str  # "env" or "keyvault"
    key: str
    vault_name: str | None = None


class SecretsResolver:
    """Resolves secret references in bundle configuration."""

    def __init__(self, keyvault_client: Any | None = None):
        self._keyvault_client = keyvault_client
        self._cache: dict[str, str] = {}

    def _get_keyvault_client(self, vault_name: str) -> Any:
        """Get or create a KeyVault client."""
        if self._keyvault_client:
            return self._keyvault_client
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            vault_url = f"https://{vault_name}.vault.azure.net"
            credential = DefaultAzureCredential()
            return SecretClient(vault_url=vault_url, credential=credential)
        except ImportError:
            raise RuntimeError(
                "Azure KeyVault SDK not installed. "
                "Install with: pip install azure-keyvault-secrets azure-identity"
            )

    def resolve_env_secret(self, var_name: str) -> str:
        """Resolve a secret from an environment variable."""
        value = os.environ.get(var_name)
        if value is None:
            raise ValueError(f"Secret environment variable '{var_name}' not set")
        return value

    def resolve_keyvault_secret(self, vault_name: str, secret_name: str) -> str:
        """Resolve a secret from Azure KeyVault."""
        cache_key = f"{vault_name}/{secret_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        client = self._get_keyvault_client(vault_name)
        secret = client.get_secret(secret_name)
        value = secret.value
        self._cache[cache_key] = value
        return value

    def resolve_string(self, value: str) -> str:
        """Resolve all secret references in a string."""
        # Resolve KeyVault secrets
        def replace_keyvault(match: re.Match) -> str:
            vault_name = match.group(1)
            secret_name = match.group(2)
            return self.resolve_keyvault_secret(vault_name, secret_name)

        result = KEYVAULT_PATTERN.sub(replace_keyvault, value)

        # Resolve environment secrets
        def replace_env(match: re.Match) -> str:
            var_name = match.group(1)
            return self.resolve_env_secret(var_name)

        result = SECRET_PATTERN.sub(replace_env, result)
        return result

    def resolve_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively resolve all secret references in a dictionary."""
        resolved = {}
        for key, value in data.items():
            if isinstance(value, str):
                resolved[key] = self.resolve_string(value)
            elif isinstance(value, dict):
                resolved[key] = self.resolve_dict(value)
            elif isinstance(value, list):
                resolved[key] = [
                    self.resolve_string(v) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                resolved[key] = value
        return resolved
