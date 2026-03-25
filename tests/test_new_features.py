"""Tests for v0.2.0 features: state management, secrets, deployer enhancements."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fab_bundle.engine.state import (
    DeploymentState,
    ResourceState,
    StateManager,
    compute_definition_hash,
)
from fab_bundle.engine.secrets import SecretsResolver


# ---------------------------------------------------------------------------
# State management tests
# ---------------------------------------------------------------------------


class TestResourceState:
    def test_round_trip(self):
        rs = ResourceState(
            item_id="abc-123",
            item_type="Notebook",
            resource_key="my-notebook",
            definition_hash="deadbeef",
            last_deployed=1000.0,
        )
        d = rs.to_dict()
        restored = ResourceState.from_dict(d)
        assert restored.item_id == "abc-123"
        assert restored.item_type == "Notebook"
        assert restored.definition_hash == "deadbeef"

    def test_from_dict_extra_keys(self):
        """Extra keys in dict should be ignored."""
        rs = ResourceState.from_dict({
            "item_id": "x",
            "item_type": "Lakehouse",
            "resource_key": "lh",
            "unknown_field": "ignored",
        })
        assert rs.item_id == "x"


class TestDeploymentState:
    def test_round_trip(self):
        state = DeploymentState(
            bundle_name="test-bundle",
            bundle_version="0.2.0",
            target_name="dev",
            workspace_id="ws-123",
            workspace_name="test-dev",
            last_deployed=1000.0,
            resources={
                "nb1": ResourceState(
                    item_id="id1", item_type="Notebook", resource_key="nb1"
                ),
            },
        )
        d = state.to_dict()
        restored = DeploymentState.from_dict(d)
        assert restored.bundle_name == "test-bundle"
        assert "nb1" in restored.resources
        assert restored.resources["nb1"].item_id == "id1"

    def test_from_empty_dict(self):
        state = DeploymentState.from_dict({})
        assert state.bundle_name == ""
        assert state.resources == {}


class TestStateManager:
    def test_load_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(Path(tmpdir), "dev")
            state = mgr.load()
            assert state.target_name == "dev"
            assert state.resources == {}

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(Path(tmpdir), "dev")
            state = mgr.record_deployment(
                bundle_name="test",
                bundle_version="0.1.0",
                workspace_id="ws-1",
                workspace_name="test-dev",
                deployed_items={
                    "notebook-1": {"id": "n1", "type": "Notebook", "definition_hash": "abc"},
                    "lakehouse-1": {"id": "l1", "type": "Lakehouse"},
                },
            )
            assert len(state.resources) == 2

            loaded = mgr.load()
            assert loaded.bundle_name == "test"
            assert loaded.workspace_id == "ws-1"
            assert "notebook-1" in loaded.resources
            assert loaded.resources["notebook-1"].item_id == "n1"

    def test_remove_resource(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(Path(tmpdir), "dev")
            mgr.record_deployment(
                bundle_name="test",
                bundle_version="0.1.0",
                workspace_id="ws-1",
                workspace_name="test-dev",
                deployed_items={"nb1": {"id": "n1", "type": "Notebook"}},
            )
            mgr.remove_resource("nb1")
            loaded = mgr.load()
            assert "nb1" not in loaded.resources

    def test_detect_drift_added(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(Path(tmpdir), "dev")
            mgr.record_deployment(
                bundle_name="test",
                bundle_version="0.1.0",
                workspace_id="ws-1",
                workspace_name="test-dev",
                deployed_items={"nb1": {"id": "n1", "type": "Notebook"}},
            )
            live = {
                "nb1": {"id": "n1", "type": "Notebook"},
                "nb2": {"id": "n2", "type": "Notebook"},
            }
            drift = mgr.detect_drift(live)
            assert drift == {"nb2": "added"}

    def test_detect_drift_removed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(Path(tmpdir), "dev")
            mgr.record_deployment(
                bundle_name="test",
                bundle_version="0.1.0",
                workspace_id="ws-1",
                workspace_name="test-dev",
                deployed_items={
                    "nb1": {"id": "n1", "type": "Notebook"},
                    "nb2": {"id": "n2", "type": "Notebook"},
                },
            )
            live = {"nb1": {"id": "n1", "type": "Notebook"}}
            drift = mgr.detect_drift(live)
            assert drift == {"nb2": "removed"}

    def test_detect_drift_modified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(Path(tmpdir), "dev")
            mgr.record_deployment(
                bundle_name="test",
                bundle_version="0.1.0",
                workspace_id="ws-1",
                workspace_name="test-dev",
                deployed_items={"nb1": {"id": "n1", "type": "Notebook"}},
            )
            live = {"nb1": {"id": "different-id", "type": "Notebook"}}
            drift = mgr.detect_drift(live)
            assert drift == {"nb1": "modified"}

    def test_no_drift(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(Path(tmpdir), "dev")
            mgr.record_deployment(
                bundle_name="test",
                bundle_version="0.1.0",
                workspace_id="ws-1",
                workspace_name="test-dev",
                deployed_items={"nb1": {"id": "n1", "type": "Notebook"}},
            )
            live = {"nb1": {"id": "n1", "type": "Notebook"}}
            drift = mgr.detect_drift(live)
            assert drift == {}

    def test_gitignore_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(Path(tmpdir), "dev")
            mgr.record_deployment(
                bundle_name="test",
                bundle_version="0.1.0",
                workspace_id="ws-1",
                workspace_name="test-dev",
                deployed_items={},
            )
            gitignore = Path(tmpdir) / ".fab-bundle" / ".gitignore"
            assert gitignore.exists()


class TestDefinitionHash:
    def test_hash_none(self):
        assert compute_definition_hash(None) is None

    def test_hash_deterministic(self):
        d = {"parts": [{"path": "a.py", "payload": "abc"}]}
        h1 = compute_definition_hash(d)
        h2 = compute_definition_hash(d)
        assert h1 == h2

    def test_hash_different_for_different_input(self):
        d1 = {"parts": [{"path": "a.py"}]}
        d2 = {"parts": [{"path": "b.py"}]}
        assert compute_definition_hash(d1) != compute_definition_hash(d2)

    def test_hash_key_order_independent(self):
        d1 = {"b": 2, "a": 1}
        d2 = {"a": 1, "b": 2}
        assert compute_definition_hash(d1) == compute_definition_hash(d2)


# ---------------------------------------------------------------------------
# Secrets tests
# ---------------------------------------------------------------------------


class TestSecretsResolver:
    def test_resolve_env_secret(self):
        resolver = SecretsResolver()
        with patch.dict(os.environ, {"MY_SECRET": "secret_value"}):
            result = resolver.resolve_string("prefix-${secret.MY_SECRET}-suffix")
            assert result == "prefix-secret_value-suffix"

    def test_resolve_env_secret_missing(self):
        resolver = SecretsResolver()
        with pytest.raises(ValueError, match="not set"):
            resolver.resolve_string("${secret.MISSING_VAR}")

    def test_resolve_no_secrets(self):
        resolver = SecretsResolver()
        assert resolver.resolve_string("plain string") == "plain string"

    def test_resolve_dict(self):
        resolver = SecretsResolver()
        with patch.dict(os.environ, {"DB_PASS": "p@ss"}):
            result = resolver.resolve_dict({
                "host": "localhost",
                "password": "${secret.DB_PASS}",
                "nested": {"key": "${secret.DB_PASS}"},
            })
            assert result["password"] == "p@ss"
            assert result["nested"]["key"] == "p@ss"
            assert result["host"] == "localhost"

    def test_resolve_list_in_dict(self):
        resolver = SecretsResolver()
        with patch.dict(os.environ, {"TOKEN": "tok123"}):
            result = resolver.resolve_dict({
                "tokens": ["${secret.TOKEN}", "plain"],
            })
            assert result["tokens"] == ["tok123", "plain"]

    def test_keyvault_pattern_detected(self):
        """KeyVault pattern should be recognized (actual resolution needs Azure SDK)."""
        resolver = SecretsResolver()
        mock_client = MagicMock()
        mock_client.get_secret.return_value = MagicMock(value="kv-secret")
        resolver._keyvault_client = mock_client

        result = resolver.resolve_string("${keyvault.my-vault.my-secret}")
        assert result == "kv-secret"
        mock_client.get_secret.assert_called_once_with("my-secret")

    def test_keyvault_caching(self):
        resolver = SecretsResolver()
        mock_client = MagicMock()
        mock_client.get_secret.return_value = MagicMock(value="cached")
        resolver._keyvault_client = mock_client

        resolver.resolve_string("${keyvault.vault.secret1}")
        resolver.resolve_string("${keyvault.vault.secret1}")
        # Should only call once due to caching
        assert mock_client.get_secret.call_count == 1


# ---------------------------------------------------------------------------
# Deployer feature tests (unit-level, mocked)
# ---------------------------------------------------------------------------


class TestDeployerRollback:
    def test_rollback_stack_populated_on_create(self):
        """Verify rollback stack is populated when items are created."""
        from fab_bundle.engine.deployer import Deployer, DeployResult
        from fab_bundle.engine.planner import PlanAction, PlanItem

        mock_client = MagicMock()
        mock_client.create_item.return_value = {"id": "new-item-id"}

        bundle = MagicMock()
        bundle.resources.get_resource_type.return_value = "notebooks"
        bundle.resources.notebooks = {}

        deployer = Deployer(mock_client, bundle, Path("/tmp"))

        item = PlanItem(
            resource_key="test-nb",
            resource_type="Notebook",
            action=PlanAction.CREATE,
        )

        result = deployer._deploy_item("ws-1", item, {})
        assert result is True
        assert len(deployer._rollback_stack) == 1
        assert deployer._rollback_stack[0]["item_id"] == "new-item-id"
