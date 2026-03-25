"""
Remote state backends for deployment state persistence.

Supports:
- local: File-based state in .fab-bundle/ (default)
- onelake: OneLake (Fabric lakehouse) — recommended for Fabric projects
- azureblob: Azure Blob Storage
- adls: Azure Data Lake Storage Gen2

Configuration in fabric.yml:

    # Recommended — store state in a Fabric lakehouse via OneLake
    state:
      backend: onelake
      config:
        workspace_id: "your-workspace-guid"
        lakehouse_id: "your-lakehouse-guid"
        # Optional: subfolder (default: .fab-bundle-state)
        path: ".fab-bundle-state"

    # Alternative — Azure Blob Storage
    state:
      backend: azureblob
      config:
        account_name: mystorageaccount
        container_name: fab-bundle-state

    # Alternative — ADLS Gen2
    state:
      backend: adls
      config:
        account_name: mydatalake
        filesystem: fab-bundle-state
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class StateBackend(ABC):
    """Abstract base class for state storage backends."""

    @abstractmethod
    def read(self, key: str) -> dict[str, Any] | None:
        """Read state by key. Returns None if not found."""

    @abstractmethod
    def write(self, key: str, data: dict[str, Any]) -> None:
        """Write state data."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete state by key."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if state exists."""

    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]:
        """List all state keys with optional prefix."""

    @abstractmethod
    def acquire_lock(self, key: str, owner: str, timeout_seconds: int = 1800) -> bool:
        """Acquire a distributed lock. Returns True if acquired."""

    @abstractmethod
    def release_lock(self, key: str) -> None:
        """Release a distributed lock."""

    @abstractmethod
    def get_lock_info(self, key: str) -> dict[str, Any] | None:
        """Get lock info, or None if unlocked."""


class LocalBackend(StateBackend):
    """Local file-based state backend (default)."""

    def __init__(self, state_dir: Path):
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._state_dir / f"{key}.json"

    def read(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def write(self, key: str, data: dict[str, Any]) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def list_keys(self, prefix: str = "") -> list[str]:
        keys = []
        for f in self._state_dir.glob("*.json"):
            key = f.stem
            if key.startswith(prefix):
                keys.append(key)
        return sorted(keys)

    def acquire_lock(self, key: str, owner: str, timeout_seconds: int = 1800) -> bool:
        import time
        lock_path = self._state_dir / f"{key}.lock"
        if lock_path.exists():
            try:
                lock_data = json.loads(lock_path.read_text())
                if time.time() - lock_data.get("timestamp", 0) > timeout_seconds:
                    pass  # Stale lock, override
                else:
                    return False
            except (json.JSONDecodeError, OSError):
                pass

        lock_data = {"owner": owner, "timestamp": time.time()}
        lock_path.write_text(json.dumps(lock_data))
        return True

    def release_lock(self, key: str) -> None:
        lock_path = self._state_dir / f"{key}.lock"
        if lock_path.exists():
            lock_path.unlink()

    def get_lock_info(self, key: str) -> dict[str, Any] | None:
        lock_path = self._state_dir / f"{key}.lock"
        if not lock_path.exists():
            return None
        try:
            return json.loads(lock_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None


class AzureBlobBackend(StateBackend):
    """Azure Blob Storage state backend with blob lease locking."""

    def __init__(self, config: dict[str, str]):
        self._account_name = config["account_name"]
        self._container_name = config.get("container_name", "fab-bundle-state")
        self._account_key = config.get("account_key")
        self._prefix = config.get("prefix", "")
        self._client = None

    def _get_container_client(self):
        if self._client:
            return self._client

        from azure.storage.blob import ContainerClient

        if self._account_key:
            conn_str = (
                f"DefaultEndpointsProtocol=https;"
                f"AccountName={self._account_name};"
                f"AccountKey={self._account_key};"
                f"EndpointSuffix=core.windows.net"
            )
            self._client = ContainerClient.from_connection_string(conn_str, self._container_name)
        else:
            from azure.identity import DefaultAzureCredential
            account_url = f"https://{self._account_name}.blob.core.windows.net"
            self._client = ContainerClient(account_url, self._container_name, credential=DefaultAzureCredential())

        # Ensure container exists
        try:
            self._client.create_container()
        except Exception:
            pass  # Already exists

        return self._client

    def _blob_name(self, key: str) -> str:
        if self._prefix:
            return f"{self._prefix}/{key}.json"
        return f"{key}.json"

    def read(self, key: str) -> dict[str, Any] | None:
        try:
            container = self._get_container_client()
            blob = container.get_blob_client(self._blob_name(key))
            data = blob.download_blob().readall()
            return json.loads(data)
        except Exception:
            return None

    def write(self, key: str, data: dict[str, Any]) -> None:
        container = self._get_container_client()
        blob = container.get_blob_client(self._blob_name(key))
        blob.upload_blob(
            json.dumps(data, indent=2, default=str).encode("utf-8"),
            overwrite=True,
        )

    def delete(self, key: str) -> None:
        try:
            container = self._get_container_client()
            blob = container.get_blob_client(self._blob_name(key))
            blob.delete_blob()
        except Exception:
            pass

    def exists(self, key: str) -> bool:
        try:
            container = self._get_container_client()
            blob = container.get_blob_client(self._blob_name(key))
            blob.get_blob_properties()
            return True
        except Exception:
            return False

    def list_keys(self, prefix: str = "") -> list[str]:
        try:
            container = self._get_container_client()
            search = self._prefix + "/" + prefix if self._prefix else prefix
            keys = []
            for blob in container.list_blobs(name_starts_with=search):
                name = blob.name
                if name.endswith(".json") and not name.endswith(".lock"):
                    key = name.rsplit("/", 1)[-1].replace(".json", "")
                    keys.append(key)
            return sorted(keys)
        except Exception:
            return []

    def acquire_lock(self, key: str, owner: str, timeout_seconds: int = 1800) -> bool:
        """Acquire lock using Azure Blob lease."""
        import time
        try:
            container = self._get_container_client()
            lock_blob_name = self._blob_name(key).replace(".json", ".lock")
            blob = container.get_blob_client(lock_blob_name)

            # Ensure lock blob exists
            try:
                blob.get_blob_properties()
            except Exception:
                blob.upload_blob(json.dumps({"owner": owner, "timestamp": time.time()}).encode(), overwrite=True)

            # Try to acquire lease (60s, renewable)
            lease = blob.acquire_lease(lease_duration=60)
            # Write lock info
            blob.upload_blob(
                json.dumps({"owner": owner, "timestamp": time.time(), "lease_id": lease.id}).encode(),
                overwrite=True,
                lease=lease,
            )
            self._lease = lease
            return True
        except Exception:
            return False

    def release_lock(self, key: str) -> None:
        try:
            if hasattr(self, "_lease") and self._lease:
                self._lease.release()
                self._lease = None
        except Exception:
            pass

    def get_lock_info(self, key: str) -> dict[str, Any] | None:
        try:
            container = self._get_container_client()
            lock_blob_name = self._blob_name(key).replace(".json", ".lock")
            blob = container.get_blob_client(lock_blob_name)
            props = blob.get_blob_properties()
            if props.lease.status == "locked":
                data = blob.download_blob().readall()
                return json.loads(data)
            return None
        except Exception:
            return None


class ADLSBackend(StateBackend):
    """Azure Data Lake Storage Gen2 state backend."""

    def __init__(self, config: dict[str, str]):
        self._account_name = config["account_name"]
        self._filesystem = config.get("filesystem", "fab-bundle-state")
        self._prefix = config.get("prefix", "")
        self._client = None

    def _get_fs_client(self):
        if self._client:
            return self._client

        from azure.identity import DefaultAzureCredential
        from azure.storage.filedatalake import DataLakeServiceClient

        account_url = f"https://{self._account_name}.dfs.core.windows.net"
        service = DataLakeServiceClient(account_url, credential=DefaultAzureCredential())
        self._client = service.get_file_system_client(self._filesystem)

        try:
            self._client.create_file_system()
        except Exception:
            pass

        return self._client

    def _file_path(self, key: str) -> str:
        if self._prefix:
            return f"{self._prefix}/{key}.json"
        return f"{key}.json"

    def read(self, key: str) -> dict[str, Any] | None:
        try:
            fs = self._get_fs_client()
            file = fs.get_file_client(self._file_path(key))
            data = file.download_file().readall()
            return json.loads(data)
        except Exception:
            return None

    def write(self, key: str, data: dict[str, Any]) -> None:
        fs = self._get_fs_client()
        file = fs.get_file_client(self._file_path(key))
        content = json.dumps(data, indent=2, default=str).encode("utf-8")
        file.upload_data(content, overwrite=True)

    def delete(self, key: str) -> None:
        try:
            fs = self._get_fs_client()
            file = fs.get_file_client(self._file_path(key))
            file.delete_file()
        except Exception:
            pass

    def exists(self, key: str) -> bool:
        try:
            fs = self._get_fs_client()
            file = fs.get_file_client(self._file_path(key))
            file.get_file_properties()
            return True
        except Exception:
            return False

    def list_keys(self, prefix: str = "") -> list[str]:
        try:
            fs = self._get_fs_client()
            search = self._prefix + "/" + prefix if self._prefix else prefix
            keys = []
            for path in fs.get_paths(path=search):
                if path.name.endswith(".json") and not path.name.endswith(".lock"):
                    key = path.name.rsplit("/", 1)[-1].replace(".json", "")
                    keys.append(key)
            return sorted(keys)
        except Exception:
            return []

    def acquire_lock(self, key: str, owner: str, timeout_seconds: int = 1800) -> bool:
        import time
        try:
            fs = self._get_fs_client()
            lock_path = self._file_path(key).replace(".json", ".lock")
            file = fs.get_file_client(lock_path)
            try:
                file.get_file_properties()
            except Exception:
                file.upload_data(json.dumps({"owner": owner, "timestamp": time.time()}).encode(), overwrite=True)
            lease = file.acquire_lease(lease_duration=60)
            self._lease = lease
            return True
        except Exception:
            return False

    def release_lock(self, key: str) -> None:
        try:
            if hasattr(self, "_lease") and self._lease:
                self._lease.release()
                self._lease = None
        except Exception:
            pass

    def get_lock_info(self, key: str) -> dict[str, Any] | None:
        try:
            fs = self._get_fs_client()
            lock_path = self._file_path(key).replace(".json", ".lock")
            file = fs.get_file_client(lock_path)
            props = file.get_file_properties()
            if props.lease.status == "locked":
                data = file.download_file().readall()
                return json.loads(data)
            return None
        except Exception:
            return None


class OneLakeBackend(StateBackend):
    """OneLake (Fabric lakehouse) state backend.

    Stores state files in a lakehouse's Files section via the OneLake ADLS-compatible endpoint.
    This is the recommended backend for Fabric projects — state lives alongside your data.

    OneLake endpoint: https://onelake.dfs.fabric.microsoft.com/
    Path format: {workspace_id}/{lakehouse_id}/Files/{path}/{key}.json
    """

    def __init__(self, config: dict[str, str]):
        self._workspace_id = config["workspace_id"]
        self._lakehouse_id = config["lakehouse_id"]
        self._path = config.get("path", ".fab-bundle-state")
        self._client = None

    def _get_fs_client(self):
        if self._client:
            return self._client

        from azure.identity import DefaultAzureCredential
        from azure.storage.filedatalake import DataLakeServiceClient

        account_url = "https://onelake.dfs.fabric.microsoft.com"
        service = DataLakeServiceClient(account_url, credential=DefaultAzureCredential())
        # OneLake filesystem = workspace_id, directory = lakehouse_id/Files/...
        self._client = service.get_file_system_client(self._workspace_id)
        return self._client

    def _file_path(self, key: str) -> str:
        return f"{self._lakehouse_id}/Files/{self._path}/{key}.json"

    def read(self, key: str) -> dict[str, Any] | None:
        try:
            fs = self._get_fs_client()
            file = fs.get_file_client(self._file_path(key))
            data = file.download_file().readall()
            return json.loads(data)
        except Exception:
            return None

    def write(self, key: str, data: dict[str, Any]) -> None:
        fs = self._get_fs_client()
        # Ensure directory exists
        dir_path = f"{self._lakehouse_id}/Files/{self._path}"
        try:
            dir_client = fs.get_directory_client(dir_path)
            dir_client.create_directory()
        except Exception:
            pass  # Already exists

        file = fs.get_file_client(self._file_path(key))
        content = json.dumps(data, indent=2, default=str).encode("utf-8")
        file.upload_data(content, overwrite=True)

    def delete(self, key: str) -> None:
        try:
            fs = self._get_fs_client()
            file = fs.get_file_client(self._file_path(key))
            file.delete_file()
        except Exception:
            pass

    def exists(self, key: str) -> bool:
        try:
            fs = self._get_fs_client()
            file = fs.get_file_client(self._file_path(key))
            file.get_file_properties()
            return True
        except Exception:
            return False

    def list_keys(self, prefix: str = "") -> list[str]:
        try:
            fs = self._get_fs_client()
            dir_path = f"{self._lakehouse_id}/Files/{self._path}"
            keys = []
            for path in fs.get_paths(path=dir_path):
                name = path.name.split("/")[-1]
                if name.endswith(".json") and not name.endswith(".lock"):
                    key = name.replace(".json", "")
                    if key.startswith(prefix):
                        keys.append(key)
            return sorted(keys)
        except Exception:
            return []

    def acquire_lock(self, key: str, owner: str, timeout_seconds: int = 1800) -> bool:
        import time
        try:
            fs = self._get_fs_client()
            lock_path = self._file_path(key).replace(".json", ".lock")
            file = fs.get_file_client(lock_path)

            # Ensure lock file exists
            try:
                file.get_file_properties()
            except Exception:
                file.upload_data(json.dumps({"owner": owner, "timestamp": time.time()}).encode(), overwrite=True)

            # Acquire lease
            lease = file.acquire_lease(lease_duration=60)
            file.upload_data(
                json.dumps({"owner": owner, "timestamp": time.time(), "lease_id": lease.id}).encode(),
                overwrite=True,
                lease=lease,
            )
            self._lease = lease
            return True
        except Exception:
            return False

    def release_lock(self, key: str) -> None:
        try:
            if hasattr(self, "_lease") and self._lease:
                self._lease.release()
                self._lease = None
        except Exception:
            pass

    def get_lock_info(self, key: str) -> dict[str, Any] | None:
        try:
            fs = self._get_fs_client()
            lock_path = self._file_path(key).replace(".json", ".lock")
            file = fs.get_file_client(lock_path)
            props = file.get_file_properties()
            if props.lease.status == "locked":
                data = file.download_file().readall()
                return json.loads(data)
            return None
        except Exception:
            return None


def create_backend(backend_type: str = "local", config: dict[str, Any] | None = None, project_dir: Path | None = None) -> StateBackend:
    """Factory function to create a state backend."""
    config = config or {}

    if backend_type == "local":
        state_dir = (project_dir or Path.cwd()) / ".fab-bundle"
        return LocalBackend(state_dir)
    elif backend_type == "azureblob":
        if "account_name" not in config:
            raise ValueError("Azure Blob backend requires 'account_name' in config")
        return AzureBlobBackend(config)
    elif backend_type == "adls":
        if "account_name" not in config:
            raise ValueError("ADLS backend requires 'account_name' in config")
        return ADLSBackend(config)
    elif backend_type == "onelake":
        if "workspace_id" not in config or "lakehouse_id" not in config:
            raise ValueError("OneLake backend requires 'workspace_id' and 'lakehouse_id' in config")
        return OneLakeBackend(config)
    else:
        raise ValueError(f"Unknown state backend: {backend_type}. Supported: local, azureblob, adls")
