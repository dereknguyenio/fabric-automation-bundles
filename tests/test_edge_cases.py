"""Additional edge case tests for Fabric Asset Bundles."""

import pytest
import yaml
from pathlib import Path

from fab_bundle.engine.loader import BundleLoadError, load_bundle
from fab_bundle.engine.resolver import (
    build_dependency_graph,
    topological_sort,
    DependencyResolutionError,
)
from fab_bundle.engine.planner import PlanAction, create_plan, DeploymentPlan
from fab_bundle.models.bundle import (
    BundleDefinition,
    ResourcesConfig,
    NotebookResource,
    LakehouseResource,
    EnvironmentResource,
    PipelineResource,
    PipelineActivity,
    TargetConfig,
    WorkspaceConfig,
    SecurityConfig,
    SecurityRole,
    OneLakeRoleBinding,
)


def write_bundle(tmp_path: Path, data: dict) -> Path:
    bundle_file = tmp_path / "fabric.yml"
    with open(bundle_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
    return bundle_file


# ---------------------------------------------------------------------------
# Circular Dependency Detection
# ---------------------------------------------------------------------------

class TestCircularDependencies:
    def test_self_referencing_notebook(self):
        """Notebook referencing itself as lakehouse should not cause issues."""
        data = {
            "bundle": {"name": "self-ref"},
            "resources": {
                "lakehouses": {"lh1": {}},
                "notebooks": {
                    "nb1": {"path": "./nb.py", "default_lakehouse": "lh1"},
                },
            },
        }
        bundle = BundleDefinition.model_validate(data)
        graph = build_dependency_graph(bundle.resources)
        result = topological_sort(graph)
        keys = [n.key for n in result]
        assert keys.index("lh1") < keys.index("nb1")

    def test_pipeline_referencing_itself_fails(self):
        """A pipeline that references itself in activities should still work
        (it references a notebook, not itself)."""
        data = {
            "bundle": {"name": "pipe-test"},
            "resources": {
                "notebooks": {"nb1": {"path": "./nb.py"}},
                "pipelines": {
                    "p1": {
                        "activities": [
                            {"notebook": "nb1"},
                        ],
                    },
                },
            },
        }
        bundle = BundleDefinition.model_validate(data)
        graph = build_dependency_graph(bundle.resources)
        result = topological_sort(graph)
        keys = [n.key for n in result]
        assert keys.index("nb1") < keys.index("p1")


# ---------------------------------------------------------------------------
# Variable Substitution
# ---------------------------------------------------------------------------

class TestVariableSubstitution:
    def test_variable_in_workspace_name(self, tmp_path):
        data = {
            "bundle": {"name": "var-test"},
            "variables": {"env_suffix": "testing"},
            "workspace": {"name": "ws-${var.env_suffix}"},
            "resources": {},
            "targets": {
                "dev": {
                    "default": True,
                    "variables": {"env_suffix": "dev"},
                },
                "prod": {
                    "variables": {"env_suffix": "prod"},
                },
            },
        }
        bundle_file = write_bundle(tmp_path, data)

        # Load with dev target
        bundle = load_bundle(bundle_file, "dev")
        ws = bundle.get_effective_workspace("dev")
        # The variable should be substituted at load time
        assert "dev" in bundle.resolve_variables("dev").get("env_suffix", "")

    def test_nested_variables(self, tmp_path):
        data = {
            "bundle": {"name": "nested-var"},
            "variables": {
                "region": {"default": "eastus"},
                "tier": {"default": "standard"},
            },
            "resources": {
                "lakehouses": {
                    "data_lh": {"description": "Region: ${var.region}, Tier: ${var.tier}"},
                },
            },
        }
        bundle_file = write_bundle(tmp_path, data)
        bundle = load_bundle(bundle_file)
        assert bundle.resources.lakehouses["data_lh"].description == "Region: eastus, Tier: standard"

    def test_unresolved_variable_left_as_is(self, tmp_path):
        data = {
            "bundle": {"name": "unresolved"},
            "resources": {
                "lakehouses": {
                    "lh": {"description": "Value: ${var.nonexistent}"},
                },
            },
        }
        bundle_file = write_bundle(tmp_path, data)
        bundle = load_bundle(bundle_file)
        assert "${var.nonexistent}" in bundle.resources.lakehouses["lh"].description


# ---------------------------------------------------------------------------
# Include Merging
# ---------------------------------------------------------------------------

class TestIncludes:
    def test_multiple_includes(self, tmp_path):
        # Create included files
        nb_data = {
            "resources": {
                "notebooks": {
                    "nb-from-include": {"path": "./nb.py"},
                },
            },
        }
        pipe_data = {
            "resources": {
                "pipelines": {
                    "pipe-from-include": {},
                },
            },
        }
        with open(tmp_path / "notebooks.yml", "w") as f:
            yaml.dump(nb_data, f)
        with open(tmp_path / "pipelines.yml", "w") as f:
            yaml.dump(pipe_data, f)

        # Main bundle
        main = {
            "bundle": {"name": "multi-include"},
            "include": ["notebooks.yml", "pipelines.yml"],
            "resources": {
                "lakehouses": {"main_lh": {}},
            },
        }
        bundle_file = write_bundle(tmp_path, main)
        bundle = load_bundle(bundle_file)

        assert "main_lh" in bundle.resources.lakehouses
        assert "nb-from-include" in bundle.resources.notebooks
        assert "pipe-from-include" in bundle.resources.pipelines

    def test_glob_includes(self, tmp_path):
        # Create resources directory with multiple files
        resources_dir = tmp_path / "resources"
        resources_dir.mkdir()

        with open(resources_dir / "lakehouses.yml", "w") as f:
            yaml.dump({"resources": {"lakehouses": {"glob_lh": {}}}}, f)

        with open(resources_dir / "notebooks.yml", "w") as f:
            yaml.dump({"resources": {"notebooks": {"glob-nb": {"path": "./nb.py"}}}}, f)

        main = {
            "bundle": {"name": "glob-test"},
            "include": ["resources/*.yml"],
            "resources": {},
        }
        bundle_file = write_bundle(tmp_path, main)
        bundle = load_bundle(bundle_file)

        assert "glob_lh" in bundle.resources.lakehouses
        assert "glob-nb" in bundle.resources.notebooks


# ---------------------------------------------------------------------------
# Security Configuration
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_multiple_role_types(self):
        data = {
            "bundle": {"name": "sec-test"},
            "resources": {},
            "security": {
                "roles": [
                    {
                        "name": "group-role",
                        "entra_group": "sg-engineers",
                        "workspace_role": "contributor",
                    },
                    {
                        "name": "user-role",
                        "entra_user": "user@company.com",
                        "workspace_role": "viewer",
                    },
                    {
                        "name": "sp-role",
                        "service_principal": "sp-automation",
                        "workspace_role": "admin",
                    },
                ],
            },
        }
        bundle = BundleDefinition.model_validate(data)
        assert len(bundle.security.roles) == 3
        assert bundle.security.roles[0].entra_group == "sg-engineers"
        assert bundle.security.roles[1].entra_user == "user@company.com"
        assert bundle.security.roles[2].service_principal == "sp-automation"

    def test_onelake_roles(self):
        data = {
            "bundle": {"name": "onelake-sec"},
            "resources": {},
            "security": {
                "roles": [
                    {
                        "name": "restricted",
                        "entra_group": "sg-restricted",
                        "workspace_role": "viewer",
                        "onelake_roles": [
                            {
                                "tables": ["public_data", "summary"],
                                "permissions": ["read"],
                            },
                        ],
                    },
                ],
            },
        }
        bundle = BundleDefinition.model_validate(data)
        role = bundle.security.roles[0]
        assert len(role.onelake_roles) == 1
        assert "public_data" in role.onelake_roles[0].tables
        assert "read" in [p.value for p in role.onelake_roles[0].permissions]


# ---------------------------------------------------------------------------
# Planner Edge Cases
# ---------------------------------------------------------------------------

class TestPlannerEdgeCases:
    def test_plan_empty_bundle(self):
        data = {"bundle": {"name": "empty"}, "resources": {}}
        bundle = BundleDefinition.model_validate(data)
        plan = create_plan(bundle, None)
        assert not plan.has_changes

    def test_plan_warns_about_unmanaged(self):
        data = {
            "bundle": {"name": "partial"},
            "resources": {"lakehouses": {"managed_lh": {}}},
        }
        bundle = BundleDefinition.model_validate(data)
        existing = {
            "managed_lh": {"id": "1", "type": "Lakehouse"},
            "unmanaged-nb": {"id": "2", "type": "Notebook"},
            "unmanaged-pipe": {"id": "3", "type": "DataPipeline"},
        }
        plan = create_plan(bundle, None, workspace_items=existing, auto_delete=False)
        assert len(plan.warnings) > 0
        assert "unmanaged" in plan.warnings[0].lower() or "not managed" in plan.warnings[0].lower()

    def test_plan_all_no_change(self):
        """When workspace matches bundle exactly, nothing should change."""
        data = {
            "bundle": {"name": "match"},
            "resources": {
                "lakehouses": {"lh1": {}},
                "notebooks": {"nb1": {"path": "./nb.py"}},
            },
        }
        bundle = BundleDefinition.model_validate(data)
        existing = {
            "lh1": {"id": "1", "type": "Lakehouse"},
            "nb1": {"id": "2", "type": "Notebook"},
        }
        plan = create_plan(bundle, None, workspace_items=existing)
        # Items exist -> they'll be marked as UPDATE (since we can't diff definitions offline)
        assert all(i.action in (PlanAction.UPDATE, PlanAction.NO_CHANGE) for i in plan.items)

    def test_plan_display(self, capsys):
        """Plan display should not crash."""
        data = {
            "bundle": {"name": "display-test"},
            "resources": {"lakehouses": {"lh1": {}, "lh2": {}}},
        }
        bundle = BundleDefinition.model_validate(data)
        plan = create_plan(bundle, None)
        plan.display()  # Should not raise


# ---------------------------------------------------------------------------
# Complex Dependency Graphs
# ---------------------------------------------------------------------------

class TestComplexDependencies:
    def test_diamond_dependency(self):
        """
        Diamond: env → nb1 → pipeline
                 env → nb2 → pipeline
        """
        data = {
            "bundle": {"name": "diamond"},
            "resources": {
                "environments": {"env": {"runtime": "1.3"}},
                "lakehouses": {"lh": {}},
                "notebooks": {
                    "nb1": {"path": "./nb1.py", "environment": "env", "default_lakehouse": "lh"},
                    "nb2": {"path": "./nb2.py", "environment": "env", "default_lakehouse": "lh"},
                },
                "pipelines": {
                    "pipe": {
                        "activities": [
                            {"notebook": "nb1"},
                            {"notebook": "nb2", "depends_on": ["nb1"]},
                        ],
                    },
                },
            },
        }
        bundle = BundleDefinition.model_validate(data)
        from fab_bundle.engine.resolver import get_deployment_order
        order = get_deployment_order(bundle)
        keys = [n.key for n in order]

        # env and lh must come before notebooks
        assert keys.index("env") < keys.index("nb1")
        assert keys.index("env") < keys.index("nb2")
        assert keys.index("lh") < keys.index("nb1")
        assert keys.index("lh") < keys.index("nb2")
        # notebooks before pipeline
        assert keys.index("nb1") < keys.index("pipe")
        assert keys.index("nb2") < keys.index("pipe")

    def test_wide_independent_resources(self):
        """Many independent resources with no dependencies."""
        data = {
            "bundle": {"name": "wide"},
            "resources": {
                "lakehouses": {f"lh_{i}": {} for i in range(10)},
            },
        }
        bundle = BundleDefinition.model_validate(data)
        from fab_bundle.engine.resolver import get_deployment_order
        order = get_deployment_order(bundle)
        assert len(order) == 10

    def test_deep_chain(self):
        """env → lh → nb → sm → report → agent."""
        data = {
            "bundle": {"name": "deep"},
            "resources": {
                "environments": {"env": {"runtime": "1.3"}},
                "lakehouses": {"lh": {}},
                "notebooks": {"nb": {"path": "./nb.py", "environment": "env", "default_lakehouse": "lh"}},
                "semantic_models": {"sm": {"path": "./sm/", "default_lakehouse": "lh"}},
                "reports": {"rpt": {"path": "./rpt/", "semantic_model": "sm"}},
                "data_agents": {"agent": {"sources": ["lh"]}},
            },
        }
        bundle = BundleDefinition.model_validate(data)
        from fab_bundle.engine.resolver import get_deployment_order
        order = get_deployment_order(bundle)
        keys = [n.key for n in order]

        assert keys.index("env") < keys.index("nb")
        assert keys.index("lh") < keys.index("nb")
        assert keys.index("lh") < keys.index("sm")
        assert keys.index("sm") < keys.index("rpt")
        assert keys.index("lh") < keys.index("agent")


# ---------------------------------------------------------------------------
# Target Resolution
# ---------------------------------------------------------------------------

class TestTargetResolution:
    def test_no_default_target(self):
        data = {
            "bundle": {"name": "no-default"},
            "resources": {},
            "targets": {
                "dev": {"workspace": {"name": "dev-ws"}},
                "prod": {"workspace": {"name": "prod-ws"}},
            },
        }
        bundle = BundleDefinition.model_validate(data)
        # No default, resolve_target(None) should return empty
        target = bundle.resolve_target(None)
        assert target.workspace is None

    def test_unknown_target_raises(self):
        data = {
            "bundle": {"name": "unknown"},
            "resources": {},
            "targets": {"dev": {"default": True}},
        }
        bundle = BundleDefinition.model_validate(data)
        with pytest.raises(ValueError, match="Unknown target"):
            bundle.resolve_target("nonexistent")

    def test_target_workspace_override(self):
        data = {
            "bundle": {"name": "override"},
            "workspace": {"name": "base-ws", "capacity": "F64"},
            "resources": {},
            "targets": {
                "dev": {
                    "default": True,
                    "workspace": {"name": "dev-ws", "capacity": "F2"},
                },
            },
        }
        bundle = BundleDefinition.model_validate(data)
        ws = bundle.get_effective_workspace("dev")
        assert ws.name == "dev-ws"
        assert ws.capacity == "F2"

    def test_target_inherits_base_workspace(self):
        data = {
            "bundle": {"name": "inherit"},
            "workspace": {"name": "base-ws", "capacity": "F64", "description": "Base desc"},
            "resources": {},
            "targets": {
                "dev": {
                    "default": True,
                    "workspace": {"name": "dev-ws"},
                    # No capacity override — should inherit F64
                },
            },
        }
        bundle = BundleDefinition.model_validate(data)
        ws = bundle.get_effective_workspace("dev")
        assert ws.name == "dev-ws"
        assert ws.capacity == "F64"
        assert ws.description == "Base desc"


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

class TestConnections:
    def test_connection_types(self):
        data = {
            "bundle": {"name": "conn-test"},
            "resources": {},
            "connections": {
                "adls": {
                    "type": "adls_gen2",
                    "endpoint": "https://account.dfs.core.windows.net",
                },
                "sql": {
                    "type": "azure_sql",
                    "endpoint": "server.database.windows.net",
                    "database": "mydb",
                },
                "custom": {
                    "type": "custom",
                    "endpoint": "https://api.example.com",
                    "properties": {"api_key_var": "MY_API_KEY"},
                },
            },
        }
        bundle = BundleDefinition.model_validate(data)
        assert len(bundle.connections) == 3
        assert bundle.connections["adls"].type.value == "adls_gen2"
        assert bundle.connections["sql"].database == "mydb"
        assert bundle.connections["custom"].properties["api_key_var"] == "MY_API_KEY"


# ---------------------------------------------------------------------------
# Eventhouse / RTI Resources
# ---------------------------------------------------------------------------

class TestRTIResources:
    def test_eventhouse_definition(self):
        data = {
            "bundle": {"name": "rti-test"},
            "resources": {
                "eventhouses": {
                    "telemetry_eh": {
                        "description": "IoT telemetry data",
                        "kql_scripts": ["./kql/create_tables.kql"],
                        "retention_days": 365,
                        "cache_days": 30,
                    },
                },
                "eventstreams": {
                    "iot-stream": {
                        "description": "IoT device event stream",
                        "path": "./eventstream/iot.json",
                    },
                },
            },
        }
        bundle = BundleDefinition.model_validate(data)
        eh = bundle.resources.eventhouses["telemetry_eh"]
        assert eh.retention_days == 365
        assert eh.cache_days == 30
        assert len(eh.kql_scripts) == 1
