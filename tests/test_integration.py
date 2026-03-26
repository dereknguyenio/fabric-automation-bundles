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


class TestAllItemTypes:
    """Verify every item type flows through plan → deploy without errors."""

    def _make_all_types_bundle(self, tmpdir: Path) -> Path:
        """Create a bundle with one resource of every deployable type."""
        # Create dummy files referenced by resources
        (tmpdir / "notebooks").mkdir(parents=True, exist_ok=True)
        (tmpdir / "notebooks" / "test.py").write_text("# test")
        (tmpdir / "defs").mkdir(parents=True, exist_ok=True)
        (tmpdir / "defs" / "pipeline.json").write_text('{"properties":{}}')
        (tmpdir / "defs" / "sjd.py").write_text("# spark job")
        (tmpdir / "defs" / "schema.graphql").write_text("type Query { hello: String }")
        (tmpdir / "defs" / "definition.json").write_text('{}')
        (tmpdir / "defs" / "dag.py").write_text("# dag")
        (tmpdir / "defs" / "sm").mkdir(parents=True, exist_ok=True)
        (tmpdir / "defs" / "sm" / "model.tmdl").write_text("// model")
        (tmpdir / "defs" / "report.pbir").write_text("{}")
        (tmpdir / "defs" / "function.json").write_text("{}")
        (tmpdir / "defs" / "mdf.json").write_text("{}")
        (tmpdir / "defs" / "mdb.json").write_text("{}")

        fabric_yml = {
            "bundle": {"name": "all-types-test", "version": "0.1.0"},
            "workspace": {"name": "test-workspace"},
            "resources": {
                # Types that create without definition
                "lakehouses": {"test_lh": {"description": "test"}},
                "warehouses": {"test_wh": {"description": "test"}},
                "environments": {"test_env": {"runtime": "1.3", "description": "test"}},
                "eventhouses": {"test_eh": {"description": "test"}},
                "ml_models": {"test_mlm": {"path": "defs/definition.json", "description": "test"}},
                "ml_experiments": {"test_mle": {"description": "test"}},
                "variable_libraries": {"test_vl": {"description": "test"}},
                "sql_databases": {"test_sqldb": {"description": "test"}},
                "operations_agents": {"test_opsagent": {"description": "test"}},
                # Types with definitions
                "notebooks": {"test_nb": {"path": "./notebooks/test.py", "description": "test"}},
                "pipelines": {"test_pipe": {"path": "./defs/pipeline.json", "description": "test"}},
                "spark_job_definitions": {"test_sjd": {"path": "./defs/sjd.py", "description": "test"}},
                "graphql_apis": {"test_gql": {"path": "./defs/schema.graphql", "description": "test"}},
                "copy_jobs": {"test_cj": {"path": "./defs/definition.json", "description": "test"}},
                "airflow_jobs": {"test_aj": {"path": "./defs/dag.py", "description": "test"}},
                "reflex": {"test_rx": {"path": "./defs/definition.json", "description": "test"}},
                "user_data_functions": {"test_udf": {"path": "./defs/function.json", "description": "test"}},
                "eventstreams": {"test_es": {"path": "./defs/definition.json", "description": "test"}},
                "kql_dashboards": {"test_kqld": {"path": "./defs/definition.json", "description": "test"}},
                "kql_querysets": {"test_kqlq": {"path": "./defs/definition.json", "description": "test"}},
                "ontologies": {"test_onto": {"path": "./defs/definition.json", "description": "test"}},
                "graphs": {"test_graph": {"path": "./defs/definition.json", "description": "test"}},
                "dbt_jobs": {"test_dbt": {"path": "./defs/definition.json", "description": "test"}},
                "anomaly_detectors": {"test_ad": {"path": "./defs/definition.json", "description": "test"}},
                "digital_twin_builders": {"test_dtb": {"path": "./defs/definition.json", "description": "test"}},
                "digital_twin_builder_flows": {"test_dtbf": {"path": "./defs/definition.json", "description": "test"}},
                "event_schema_sets": {"test_ess": {"path": "./defs/definition.json", "description": "test"}},
                "graph_query_sets": {"test_gqs": {"path": "./defs/definition.json", "description": "test"}},
                "map_items": {"test_map": {"path": "./defs/definition.json", "description": "test"}},
                "graph_models": {"test_gm": {"path": "./defs/definition.json", "description": "test"}},
                "hls_cohorts": {"test_hls": {"path": "./defs/definition.json", "description": "test"}},
                "dataflows": {"test_df": {"path": "./defs/definition.json", "description": "test"}},
                # Types that require definition (provide one so they don't skip)
                "semantic_models": {"test_sm": {"path": "./defs/sm", "description": "test"}},
                "reports": {"test_report": {"path": "./defs/report.pbir", "description": "test"}},
                "mounted_data_factories": {"test_mdf": {"description": "test"}},
                "mirrored_databases": {"test_mdb": {"description": "test"}},
                # KQL database with parent eventhouse
                "kql_databases": {"test_kqldb": {"parent_eventhouse": "test_eh", "description": "test"}},
                # Types that depend on connections
                "snowflake_databases": {"test_snow": {"description": "test"}},
                "cosmosdb_databases": {"test_cosmos": {"description": "test"}},
                "mirrored_databricks_catalogs": {"test_mdc": {"description": "test"}},
                # Data agents
                "data_agents": {"test_da": {"description": "test"}},
                # List-only types (should be auto-skipped)
                "datamarts": {"test_dm": {"description": "test"}},
                "dashboards": {"test_dash": {"description": "test"}},
                "paginated_reports": {"test_pr": {"description": "test"}},
                "mirrored_warehouses": {"test_mw": {"description": "test"}},
            },
            "targets": {
                "dev": {"default": True, "workspace": {"name": "test-dev"}},
            },
        }

        (tmpdir / "fabric.yml").write_text(yaml.dump(fabric_yml))
        return tmpdir

    def test_all_types_plan_produces_correct_api_types(self):
        """Every resource type should produce a valid Fabric API type name in the plan."""
        from fab_bundle.providers.fabric_api import ITEM_TYPE_MAP

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._make_all_types_bundle(Path(tmpdir))
            bundle = load_bundle(str(project_dir / "fabric.yml"), "dev")

            plan = create_plan(bundle, "dev", workspace_items={})

            # All items should be CREATE actions
            assert plan.has_changes
            assert not plan.errors

            # Every plan item's resource_type should be a proper API type name
            # (capitalized, not a field name like "kql_databases")
            valid_api_types = set(ITEM_TYPE_MAP.values())
            for item in plan.items:
                assert item.resource_type in valid_api_types, (
                    f"Plan item '{item.resource_key}' has raw field name "
                    f"'{item.resource_type}' instead of an API type name"
                )

    def test_all_types_deploy_with_mock(self):
        """Every resource type should deploy without errors using a mocked API."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._make_all_types_bundle(Path(tmpdir))
            bundle = load_bundle(str(project_dir / "fabric.yml"), "dev")

            client = _mock_client()
            # Return eventhouse in workspace items so KQL database can find parent
            client.get_workspace_items_map.return_value = {
                "test_eh": {"id": "eh-001", "type": "Eventhouse"},
            }
            # list_items must also return the Eventhouse for KQL DB parent lookup
            client.list_items.return_value = [
                {"id": "eh-001", "displayName": "test_eh", "type": "Eventhouse"},
            ]

            plan = create_plan(bundle, "dev", workspace_items={})
            assert not plan.errors

            deployer = Deployer(client, bundle, project_dir)
            result = deployer.execute(plan, "dev")

            assert result.success, f"Deploy failed with errors: {result.errors}"
            assert result.items_failed == 0, f"Failed items: {result.errors}"
            # List-only types (4) should be skipped, definition-required without
            # definition (2: MountedDataFactory, MirroredDatabase) should be skipped
            # All others should be created
            total_resources = len(plan.items)
            skipped = 4 + 2  # list-only + definition-required without definition
            assert result.items_created == total_resources - skipped, (
                f"Expected {total_resources - skipped} creates, got {result.items_created}. "
                f"Errors: {result.errors}"
            )


class TestMCPSafety:
    """MCP deploy/destroy must require confirmation."""

    def test_deploy_without_confirm_returns_plan(self):
        """fab_deploy without confirm: true should return a plan, not execute."""
        from fab_bundle.mcp_server.server import _dispatch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a minimal bundle
            fabric_yml = Path(tmpdir) / "fabric.yml"
            fabric_yml.write_text("""
bundle:
  name: test
  version: "1.0.0"
resources:
  lakehouses:
    test_lh:
      description: "test"
targets:
  dev:
    default: true
    workspace:
      name: test-dev
""")
            # Mock the client
            import unittest.mock as mock
            with mock.patch("fab_bundle.mcp_server.server._get_client") as mock_client:
                client = mock.MagicMock()
                client.find_workspace.return_value = {"id": "ws-001"}
                client.get_workspace_items_map.return_value = {}
                mock_client.return_value = client

                result = _dispatch("fab_deploy", {"project_dir": tmpdir, "target": "dev"})
                import json
                data = json.loads(result)

                assert data.get("confirmation_required") is True
                assert "message" in data
                # Should NOT have called create_item
                client.create_item.assert_not_called()

    def test_deploy_with_confirm_executes(self):
        """fab_deploy with confirm: true should execute."""
        from fab_bundle.mcp_server.server import _dispatch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            fabric_yml = Path(tmpdir) / "fabric.yml"
            fabric_yml.write_text("""
bundle:
  name: test
  version: "1.0.0"
resources:
  lakehouses:
    test_lh:
      description: "test"
targets:
  dev:
    default: true
    workspace:
      name: test-dev
""")
            import unittest.mock as mock
            with mock.patch("fab_bundle.mcp_server.server._get_client") as mock_client:
                client = mock.MagicMock()
                client.find_workspace.return_value = {"id": "ws-001"}
                client.get_workspace_items_map.return_value = {}
                client.create_item.return_value = {"id": "item-001"}
                client.create_workspace.return_value = {"id": "ws-001"}
                client.list_items.return_value = []
                mock_client.return_value = client

                result = _dispatch("fab_deploy", {"project_dir": tmpdir, "target": "dev", "confirm": True})
                import json
                data = json.loads(result)

                # Should have executed (success or failure, but not confirmation_required)
                assert "confirmation_required" not in data

    def test_destroy_without_confirm_returns_preview(self):
        """fab_destroy without confirm: true should return items list, not delete."""
        from fab_bundle.mcp_server.server import _dispatch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            fabric_yml = Path(tmpdir) / "fabric.yml"
            fabric_yml.write_text("""
bundle:
  name: test
  version: "1.0.0"
resources:
  lakehouses:
    test_lh:
      description: "test"
targets:
  dev:
    default: true
    workspace:
      name: test-dev
""")
            import unittest.mock as mock
            with mock.patch("fab_bundle.mcp_server.server._get_client") as mock_client:
                client = mock.MagicMock()
                client.find_workspace.return_value = {"id": "ws-001"}
                client.get_workspace_items_map.return_value = {
                    "test_lh": {"id": "lh-001", "type": "Lakehouse"},
                }
                mock_client.return_value = client

                result = _dispatch("fab_destroy", {"project_dir": tmpdir, "target": "dev"})
                import json
                data = json.loads(result)

                assert data.get("confirmation_required") is True
                # Should NOT have called delete_item
                client.delete_item.assert_not_called()


class TestDeployHookWarnings:
    """Post-deploy hooks should report warnings, not fail silently."""

    def test_hook_warnings_collected(self):
        """Hook failures should be collected in result.hook_warnings."""
        from fab_bundle.engine.deployer import Deployer, DeployResult

        # Verify DeployResult has hook_warnings field
        result = DeployResult(success=True)
        assert hasattr(result, "hook_warnings")
        assert result.hook_warnings == []


class TestStrictValidation:
    """Strict mode should fail on unresolved variables."""

    def test_strict_fails_on_unresolved_variables(self):
        """load_bundle with strict=True should raise on unresolved vars."""
        import tempfile
        from fab_bundle.engine.loader import BundleLoadError, load_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            fabric_yml = Path(tmpdir) / "fabric.yml"
            fabric_yml.write_text("""
bundle:
  name: test
  version: "1.0.0"
resources:
  lakehouses:
    test_lh:
      description: "${var.missing_var}"
targets:
  dev:
    default: true
    workspace:
      name: test-dev
""")
            import pytest
            with pytest.raises(BundleLoadError, match="Unresolved variables"):
                load_bundle(str(fabric_yml), strict=True)

    def test_non_strict_warns_on_unresolved_variables(self):
        """load_bundle without strict should warn but not fail."""
        import tempfile
        import warnings
        from fab_bundle.engine.loader import load_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            fabric_yml = Path(tmpdir) / "fabric.yml"
            fabric_yml.write_text("""
bundle:
  name: test
  version: "1.0.0"
resources:
  lakehouses:
    test_lh:
      description: "${var.missing_var}"
targets:
  dev:
    default: true
    workspace:
      name: test-dev
""")
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                bundle = load_bundle(str(fabric_yml))
                assert len(w) >= 1
                assert "Unresolved" in str(w[0].message)


class TestCapacityValidation:
    """capacity_id should be validated as a GUID."""

    def test_invalid_capacity_id_rejected(self):
        """Non-GUID capacity_id should fail validation."""
        import tempfile
        import pytest
        from fab_bundle.engine.loader import load_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            fabric_yml = Path(tmpdir) / "fabric.yml"
            fabric_yml.write_text("""
bundle:
  name: test
  version: "1.0.0"
resources:
  lakehouses:
    test_lh:
      description: "test"
targets:
  dev:
    default: true
    workspace:
      name: test-dev
      capacity_id: "not-a-guid"
""")
            with pytest.raises(Exception, match="not a valid GUID"):
                load_bundle(str(fabric_yml))

    def test_valid_capacity_id_accepted(self):
        """Valid GUID capacity_id should pass."""
        import tempfile
        from fab_bundle.engine.loader import load_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            fabric_yml = Path(tmpdir) / "fabric.yml"
            fabric_yml.write_text("""
bundle:
  name: test
  version: "1.0.0"
resources:
  lakehouses:
    test_lh:
      description: "test"
targets:
  dev:
    default: true
    workspace:
      name: test-dev
      capacity_id: "ee418141-2bb6-40a4-8586-1f60e290f129"
""")
            bundle = load_bundle(str(fabric_yml))
            assert bundle is not None

    def test_variable_ref_capacity_id_accepted(self):
        """Variable reference capacity_id should pass validation."""
        import tempfile
        from fab_bundle.engine.loader import load_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            fabric_yml = Path(tmpdir) / "fabric.yml"
            fabric_yml.write_text("""
bundle:
  name: test
  version: "1.0.0"
resources:
  lakehouses:
    test_lh:
      description: "test"
targets:
  dev:
    default: true
    workspace:
      name: test-dev
      capacity_id: "${var.capacity_id}"
""")
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                bundle = load_bundle(str(fabric_yml))
                assert bundle is not None
