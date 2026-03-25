"""Integration tests with mocked Fabric API — tests full deploy/destroy/drift flows."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from fab_bundle.engine.deployer import Deployer, DeployResult
from fab_bundle.engine.loader import load_bundle
from fab_bundle.engine.planner import PlanAction, create_plan
from fab_bundle.engine.state import StateManager
from fab_bundle.providers.fabric_api import FabricClient


def _make_bundle_dir(tmpdir: Path) -> Path:
    """Create a minimal bundle project for testing."""
    notebook_path = tmpdir / "notebooks" / "test.py"
    notebook_path.parent.mkdir(parents=True)
    notebook_path.write_text("# test notebook\nprint('hello')")

    fabric_yml = {
        "bundle": {"name": "test-bundle", "version": "0.1.0"},
        "workspace": {"name": "test-workspace"},
        "resources": {
            "lakehouses": {
                "test_lakehouse": {"description": "Test lakehouse"},
            },
            "notebooks": {
                "test_notebook": {
                    "path": "./notebooks/test.py",
                    "description": "Test notebook",
                },
            },
        },
        "targets": {
            "dev": {
                "default": True,
                "workspace": {"name": "test-dev"},
            },
        },
    }

    (tmpdir / "fabric.yml").write_text(yaml.dump(fabric_yml))
    return tmpdir


def _mock_client() -> MagicMock:
    """Create a mock FabricClient with realistic responses."""
    client = MagicMock(spec=FabricClient)
    client.find_workspace.return_value = {"id": "ws-123", "displayName": "test-dev"}
    client.create_workspace.return_value = {"id": "ws-new-123"}
    client.get_workspace_items_map.return_value = {}
    client.create_item.return_value = {"id": "item-001"}
    client.update_item_definition.return_value = None
    client.update_item.return_value = {}
    client.delete_item.return_value = None
    client.add_workspace_role_assignment.return_value = {}
    return client


class TestFullDeployFlow:
    def test_deploy_creates_all_resources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _make_bundle_dir(Path(tmpdir))
            bundle = load_bundle(str(project_dir / "fabric.yml"), "dev")
            client = _mock_client()

            plan = create_plan(bundle, "dev", workspace_items={})
            assert plan.has_changes
            assert len(plan.creates) == 2

            deployer = Deployer(client, bundle, project_dir)
            result = deployer.execute(plan, "dev")

            assert result.success
            assert result.items_created == 2
            assert result.items_failed == 0
            assert client.create_item.call_count == 2

    def test_deploy_with_existing_items_updates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _make_bundle_dir(Path(tmpdir))
            bundle = load_bundle(str(project_dir / "fabric.yml"), "dev")
            client = _mock_client()

            existing = {
                "test_lakehouse": {"id": "lh-001", "type": "Lakehouse"},
                "test_notebook": {"id": "nb-001", "type": "Notebook"},
            }
            client.get_workspace_items_map.return_value = existing

            plan = create_plan(bundle, "dev", workspace_items=existing)
            assert plan.has_changes
            assert len(plan.updates) == 2
            assert len(plan.creates) == 0

            deployer = Deployer(client, bundle, project_dir)
            result = deployer.execute(plan, "dev")

            assert result.success
            assert result.items_updated == 2

    def test_deploy_creates_workspace_if_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _make_bundle_dir(Path(tmpdir))
            bundle = load_bundle(str(project_dir / "fabric.yml"), "dev")
            client = _mock_client()
            client.find_workspace.return_value = None
            client.create_workspace.return_value = {"id": "ws-new"}
            client.get_workspace_items_map.return_value = {}

            plan = create_plan(bundle, "dev", workspace_items={})
            deployer = Deployer(client, bundle, project_dir)
            result = deployer.execute(plan, "dev")

            client.create_workspace.assert_called_once()
            assert result.success

    def test_deploy_saves_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _make_bundle_dir(Path(tmpdir))
            bundle = load_bundle(str(project_dir / "fabric.yml"), "dev")
            client = _mock_client()
            client.get_workspace_items_map.side_effect = [
                {},  # first call for plan
                {"test_lakehouse": {"id": "lh-1", "type": "Lakehouse"}, "test_notebook": {"id": "nb-1", "type": "Notebook"}},  # post-deploy
            ]

            plan = create_plan(bundle, "dev", workspace_items={})

            state_mgr = StateManager(project_dir, "dev")
            deployer = Deployer(client, bundle, project_dir)
            deployer.state_manager = state_mgr
            result = deployer.execute(plan, "dev")

            assert result.success
            state = state_mgr.load()
            assert state.bundle_name == "test-bundle"

    def test_deploy_rollback_on_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _make_bundle_dir(Path(tmpdir))
            bundle = load_bundle(str(project_dir / "fabric.yml"), "dev")
            client = _mock_client()

            # First create succeeds, second fails
            client.create_item.side_effect = [
                {"id": "lh-001"},
                Exception("API error"),
            ]
            client.get_workspace_items_map.return_value = {}

            plan = create_plan(bundle, "dev", workspace_items={})
            deployer = Deployer(client, bundle, project_dir)
            result = deployer.execute(plan, "dev")

            assert not result.success
            assert result.items_failed >= 1
            # Rollback should delete the first created item
            assert client.delete_item.called


class TestDestroyFlow:
    def test_plan_with_auto_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _make_bundle_dir(Path(tmpdir))
            bundle = load_bundle(str(project_dir / "fabric.yml"), "dev")

            existing = {
                "test_lakehouse": {"id": "lh-001", "type": "Lakehouse"},
                "test_notebook": {"id": "nb-001", "type": "Notebook"},
                "orphan_item": {"id": "orph-001", "type": "Notebook"},
            }

            plan = create_plan(bundle, "dev", workspace_items=existing, auto_delete=True)
            assert len(plan.deletes) == 1
            assert plan.deletes[0].resource_key == "orphan_item"


class TestDriftDetection:
    def test_drift_after_deploy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _make_bundle_dir(Path(tmpdir))
            state_mgr = StateManager(project_dir, "dev")

            state_mgr.record_deployment(
                bundle_name="test-bundle",
                bundle_version="0.1.0",
                workspace_id="ws-123",
                workspace_name="test-dev",
                deployed_items={
                    "test_lakehouse": {"id": "lh-1", "type": "Lakehouse"},
                    "test_notebook": {"id": "nb-1", "type": "Notebook"},
                },
            )

            # Simulate someone adding an item in the portal
            live_items = {
                "test_lakehouse": {"id": "lh-1", "type": "Lakehouse"},
                "test_notebook": {"id": "nb-1", "type": "Notebook"},
                "manual_notebook": {"id": "nb-99", "type": "Notebook"},
            }

            drift = state_mgr.detect_drift(live_items)
            assert "manual_notebook" in drift
            assert drift["manual_notebook"] == "added"

    def test_no_drift_when_matching(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _make_bundle_dir(Path(tmpdir))
            state_mgr = StateManager(project_dir, "dev")

            state_mgr.record_deployment(
                bundle_name="test-bundle",
                bundle_version="0.1.0",
                workspace_id="ws-123",
                workspace_name="test-dev",
                deployed_items={
                    "test_lakehouse": {"id": "lh-1", "type": "Lakehouse"},
                },
            )

            live_items = {"test_lakehouse": {"id": "lh-1", "type": "Lakehouse"}}
            drift = state_mgr.detect_drift(live_items)
            assert drift == {}


class TestStatePlan:
    def test_plan_skips_unchanged_with_state(self):
        """Items with matching state hashes should be NO_CHANGE, not UPDATE."""
        from fab_bundle.engine.state import DeploymentState, ResourceState

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _make_bundle_dir(Path(tmpdir))
            bundle = load_bundle(str(project_dir / "fabric.yml"), "dev")

            existing = {
                "test_lakehouse": {"id": "lh-001", "type": "Lakehouse"},
                "test_notebook": {"id": "nb-001", "type": "Notebook"},
            }

            state = DeploymentState(
                bundle_name="test-bundle",
                target_name="dev",
                workspace_id="ws-123",
                resources={
                    "test_lakehouse": ResourceState(
                        item_id="lh-001", item_type="Lakehouse",
                        resource_key="test_lakehouse", definition_hash="abc123",
                    ),
                    "test_notebook": ResourceState(
                        item_id="nb-001", item_type="Notebook",
                        resource_key="test_notebook", definition_hash="def456",
                    ),
                },
            )

            plan = create_plan(bundle, "dev", workspace_items=existing, state=state)
            no_change = [i for i in plan.items if i.action == PlanAction.NO_CHANGE]
            updates = [i for i in plan.items if i.action == PlanAction.UPDATE]

            assert len(no_change) == 2
            assert len(updates) == 0

    def test_plan_updates_without_state(self):
        """Without state, existing items should be marked UPDATE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _make_bundle_dir(Path(tmpdir))
            bundle = load_bundle(str(project_dir / "fabric.yml"), "dev")

            existing = {
                "test_lakehouse": {"id": "lh-001", "type": "Lakehouse"},
                "test_notebook": {"id": "nb-001", "type": "Notebook"},
            }

            plan = create_plan(bundle, "dev", workspace_items=existing)
            updates = [i for i in plan.items if i.action == PlanAction.UPDATE]
            assert len(updates) == 2


class TestNameValidation:
    def test_hyphen_in_lakehouse_name_rejected(self):
        """Lakehouse names with hyphens should fail validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            fabric_yml = {
                "bundle": {"name": "test", "version": "0.1.0"},
                "resources": {
                    "lakehouses": {
                        "my-lakehouse": {"description": "bad name"},
                    },
                },
            }
            (project_dir / "fabric.yml").write_text(yaml.dump(fabric_yml))

            with pytest.raises(Exception, match="only letters, numbers, and underscores"):
                load_bundle(str(project_dir / "fabric.yml"))

    def test_underscore_in_lakehouse_name_accepted(self):
        """Lakehouse names with underscores should pass validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            nb_path = project_dir / "test.py"
            nb_path.write_text("# test")
            fabric_yml = {
                "bundle": {"name": "test", "version": "0.1.0"},
                "resources": {
                    "lakehouses": {
                        "my_lakehouse": {"description": "good name"},
                    },
                },
            }
            (project_dir / "fabric.yml").write_text(yaml.dump(fabric_yml))
            bundle = load_bundle(str(project_dir / "fabric.yml"))
            assert "my_lakehouse" in bundle.resources.lakehouses


class TestDeploymentWaves:
    def test_waves_group_independent_resources(self):
        from fab_bundle.engine.resolver import get_deployment_waves

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _make_bundle_dir(Path(tmpdir))
            bundle = load_bundle(str(project_dir / "fabric.yml"), "dev")

            waves = get_deployment_waves(bundle)
            assert len(waves) >= 1
            # Both lakehouse and notebook should be deployable
            all_keys = [node.key for wave in waves for node in wave]
            assert "test_lakehouse" in all_keys
            assert "test_notebook" in all_keys
