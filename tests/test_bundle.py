"""Tests for Fabric Asset Bundles."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from fab_bundle.engine.loader import BundleLoadError, load_bundle, dump_bundle
from fab_bundle.engine.planner import PlanAction, create_plan
from fab_bundle.engine.resolver import (
    build_dependency_graph,
    get_deployment_order,
    DependencyResolutionError,
)
from fab_bundle.models.bundle import (
    BundleDefinition,
    BundleMetadata,
    LakehouseResource,
    NotebookResource,
    PipelineResource,
    PipelineActivity,
    ReportResource,
    ResourcesConfig,
    SemanticModelResource,
    EnvironmentResource,
    DataAgentInstructions,
    SecurityConfig,
    SecurityRole,
    TargetConfig,
    WorkspaceConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_BUNDLE = {
    "bundle": {"name": "test-bundle", "version": "1.0.0"},
    "resources": {
        "lakehouses": {
            "my_lakehouse": {"description": "test lakehouse"},
        },
    },
}


FULL_BUNDLE = {
    "bundle": {
        "name": "full-test",
        "version": "2.0.0",
        "description": "A comprehensive test bundle",
    },
    "workspace": {"name": "test-workspace", "capacity": "F64"},
    "resources": {
        "environments": {
            "spark-env": {"runtime": "1.3", "libraries": ["pandas"]},
        },
        "lakehouses": {
            "bronze": {"description": "Raw data"},
            "silver": {"description": "Clean data"},
            "gold": {"description": "Curated data"},
        },
        "notebooks": {
            "etl-bronze": {
                "path": "./notebooks/etl.py",
                "environment": "spark-env",
                "default_lakehouse": "bronze",
            },
            "etl-silver": {
                "path": "./notebooks/silver.py",
                "environment": "spark-env",
                "default_lakehouse": "silver",
            },
        },
        "pipelines": {
            "daily-refresh": {
                "activities": [
                    {"name": "step1", "notebook": "etl-bronze"},
                    {"name": "step2", "notebook": "etl-silver", "depends_on": ["etl-bronze"]},
                ],
            },
        },
        "semantic_models": {
            "analytics-model": {
                "path": "./model/",
                "default_lakehouse": "gold",
            },
        },
        "reports": {
            "dashboard": {
                "path": "./reports/dash/",
                "semantic_model": "analytics-model",
            },
        },
        "data_agents": {
            "my-agent": {
                "sources": ["gold"],
                "instructions": "./agent/instructions.md",
            },
        },
    },
    "security": {
        "roles": [
            {"name": "engineers", "entra_group": "sg-eng", "workspace_role": "contributor"},
            {"name": "viewers", "entra_group": "sg-view", "workspace_role": "viewer"},
        ],
    },
    "targets": {
        "dev": {
            "default": True,
            "workspace": {"name": "test-dev"},
            "variables": {"env": "dev"},
        },
        "prod": {
            "workspace": {"name": "test-prod"},
            "variables": {"env": "prod"},
        },
    },
}


@pytest.fixture
def tmp_bundle_dir(tmp_path):
    """Create a temp dir with a fabric.yml."""
    return tmp_path


def write_bundle(tmp_path: Path, data: dict) -> Path:
    """Write a bundle YAML to a temp directory."""
    bundle_file = tmp_path / "fabric.yml"
    with open(bundle_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
    return bundle_file


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class TestBundleModels:
    def test_minimal_bundle(self):
        bundle = BundleDefinition.model_validate(MINIMAL_BUNDLE)
        assert bundle.bundle.name == "test-bundle"
        assert bundle.bundle.version == "1.0.0"
        assert "my_lakehouse" in bundle.resources.lakehouses

    def test_full_bundle(self):
        bundle = BundleDefinition.model_validate(FULL_BUNDLE)
        assert bundle.bundle.name == "full-test"
        assert len(bundle.resources.lakehouses) == 3
        assert len(bundle.resources.notebooks) == 2
        assert len(bundle.resources.pipelines) == 1
        assert len(bundle.resources.semantic_models) == 1
        assert len(bundle.resources.reports) == 1
        assert len(bundle.resources.data_agents) == 1
        assert len(bundle.targets) == 2
        assert len(bundle.security.roles) == 2

    def test_invalid_notebook_reference(self):
        data = {
            "bundle": {"name": "test"},
            "resources": {
                "notebooks": {
                    "nb1": {"path": "./nb.py", "environment": "nonexistent-env"},
                },
            },
        }
        with pytest.raises(Exception):
            BundleDefinition.model_validate(data)

    def test_invalid_report_reference(self):
        data = {
            "bundle": {"name": "test"},
            "resources": {
                "reports": {
                    "r1": {"path": "./r.pbir", "semantic_model": "nonexistent-model"},
                },
            },
        }
        with pytest.raises(Exception):
            BundleDefinition.model_validate(data)

    def test_all_resource_keys(self):
        bundle = BundleDefinition.model_validate(FULL_BUNDLE)
        keys = bundle.resources.all_resource_keys()
        assert "bronze" in keys
        assert "etl-bronze" in keys
        assert "daily-refresh" in keys
        assert "analytics-model" in keys
        assert "dashboard" in keys
        assert "my-agent" in keys

    def test_get_resource_type(self):
        bundle = BundleDefinition.model_validate(FULL_BUNDLE)
        assert bundle.resources.get_resource_type("bronze") == "lakehouses"
        assert bundle.resources.get_resource_type("etl-bronze") == "notebooks"
        assert bundle.resources.get_resource_type("nonexistent") is None

    def test_resolve_target(self):
        bundle = BundleDefinition.model_validate(FULL_BUNDLE)
        dev = bundle.resolve_target("dev")
        assert dev.default is True

        prod = bundle.resolve_target("prod")
        assert prod.default is False

        default = bundle.resolve_target(None)
        assert default.default is True

    def test_resolve_variables(self):
        bundle = BundleDefinition.model_validate(FULL_BUNDLE)
        dev_vars = bundle.resolve_variables("dev")
        assert dev_vars.get("env") == "dev"

        prod_vars = bundle.resolve_variables("prod")
        assert prod_vars.get("env") == "prod"

    def test_effective_workspace(self):
        bundle = BundleDefinition.model_validate(FULL_BUNDLE)
        ws = bundle.get_effective_workspace("dev")
        assert ws.name == "test-dev"

        ws_prod = bundle.get_effective_workspace("prod")
        assert ws_prod.name == "test-prod"


# ---------------------------------------------------------------------------
# Loader Tests
# ---------------------------------------------------------------------------

class TestLoader:
    def test_load_minimal(self, tmp_path):
        bundle_file = write_bundle(tmp_path, MINIMAL_BUNDLE)
        bundle = load_bundle(bundle_file)
        assert bundle.bundle.name == "test-bundle"

    def test_load_full(self, tmp_path):
        bundle_file = write_bundle(tmp_path, FULL_BUNDLE)
        bundle = load_bundle(bundle_file)
        assert bundle.bundle.name == "full-test"
        assert len(bundle.resources.notebooks) == 2

    def test_load_missing_file(self):
        with pytest.raises(BundleLoadError):
            load_bundle("/nonexistent/fabric.yml")

    def test_load_invalid_yaml(self, tmp_path):
        bad_file = tmp_path / "fabric.yml"
        bad_file.write_text("{{invalid: yaml: content")
        with pytest.raises(BundleLoadError):
            load_bundle(bad_file)

    def test_dump_roundtrip(self, tmp_path):
        bundle_file = write_bundle(tmp_path, FULL_BUNDLE)
        bundle = load_bundle(bundle_file)
        yaml_str = dump_bundle(bundle)
        assert "full-test" in yaml_str
        assert "etl-bronze" in yaml_str

    def test_includes(self, tmp_path):
        # Main file
        main = {
            "bundle": {"name": "include-test"},
            "include": ["resources.yml"],
            "resources": {},
        }
        write_bundle(tmp_path, main)

        # Included file
        resources = {
            "resources": {
                "lakehouses": {"included_lh": {"description": "from include"}},
            },
        }
        with open(tmp_path / "resources.yml", "w") as f:
            yaml.dump(resources, f)

        bundle = load_bundle(tmp_path / "fabric.yml")
        assert "included_lh" in bundle.resources.lakehouses


# ---------------------------------------------------------------------------
# Resolver Tests
# ---------------------------------------------------------------------------

class TestResolver:
    def test_simple_dependency_order(self):
        bundle = BundleDefinition.model_validate(FULL_BUNDLE)
        order = get_deployment_order(bundle)
        keys = [n.key for n in order]

        # Environments must come before notebooks that use them
        assert keys.index("spark-env") < keys.index("etl-bronze")
        assert keys.index("spark-env") < keys.index("etl-silver")

        # Lakehouses must come before notebooks that use them
        assert keys.index("bronze") < keys.index("etl-bronze")
        assert keys.index("silver") < keys.index("etl-silver")

        # Notebooks must come before pipelines that use them
        assert keys.index("etl-bronze") < keys.index("daily-refresh")

        # Semantic models before reports
        assert keys.index("analytics-model") < keys.index("dashboard")

        # Sources before data agents
        assert keys.index("gold") < keys.index("my-agent")

    def test_all_resources_in_order(self):
        bundle = BundleDefinition.model_validate(FULL_BUNDLE)
        order = get_deployment_order(bundle)
        all_keys = bundle.resources.all_resource_keys()
        ordered_keys = {n.key for n in order}
        assert ordered_keys == all_keys

    def test_no_resources(self):
        bundle = BundleDefinition.model_validate(MINIMAL_BUNDLE)
        order = get_deployment_order(bundle)
        assert len(order) == 1  # Just the one lakehouse


# ---------------------------------------------------------------------------
# Planner Tests
# ---------------------------------------------------------------------------

class TestPlanner:
    def test_plan_fresh_workspace(self):
        bundle = BundleDefinition.model_validate(FULL_BUNDLE)
        plan = create_plan(bundle, "dev", workspace_items=None)

        assert plan.bundle_name == "full-test"
        assert plan.has_changes
        assert len(plan.creates) > 0
        assert len(plan.updates) == 0
        assert len(plan.deletes) == 0

    def test_plan_existing_items(self):
        bundle = BundleDefinition.model_validate(FULL_BUNDLE)
        existing = {
            "bronze": {"id": "id-1", "type": "Lakehouse"},
            "etl-bronze": {"id": "id-2", "type": "Notebook"},
        }
        plan = create_plan(bundle, "dev", workspace_items=existing)

        creates = {i.resource_key for i in plan.creates}
        updates = {i.resource_key for i in plan.updates}

        assert "bronze" in updates
        assert "etl-bronze" in updates
        assert "silver" in creates
        assert "gold" in creates

    def test_plan_auto_delete(self):
        bundle = BundleDefinition.model_validate(MINIMAL_BUNDLE)
        existing = {
            "my_lakehouse": {"id": "id-1", "type": "Lakehouse"},
            "orphaned-notebook": {"id": "id-2", "type": "Notebook"},
        }
        plan = create_plan(bundle, None, workspace_items=existing, auto_delete=True)

        deletes = {i.resource_key for i in plan.deletes}
        assert "orphaned-notebook" in deletes

    def test_plan_summary(self):
        bundle = BundleDefinition.model_validate(FULL_BUNDLE)
        plan = create_plan(bundle, "dev")
        summary = plan.summary
        assert "create" in summary


# ---------------------------------------------------------------------------
# Template Tests
# ---------------------------------------------------------------------------

class TestTemplates:
    def test_list_templates(self):
        from fab_bundle.generators.templates import list_templates
        templates = list_templates()
        names = [t["name"] for t in templates]
        assert "medallion" in names
        assert "osdu_analytics" in names or "osdu-analytics" in names

    def test_init_medallion(self, tmp_path):
        from fab_bundle.generators.templates import init_from_template
        output = tmp_path / "test-project"
        init_from_template("medallion", output, {"project_name": "test-project"})

        assert (output / "fabric.yml").exists()
        assert (output / "notebooks" / "ingest_to_bronze.py").exists()
        assert (output / "notebooks" / "bronze_to_silver.py").exists()
        assert (output / "notebooks" / "silver_to_gold.py").exists()
        assert (output / "agent" / "instructions.md").exists()

    def test_init_osdu(self, tmp_path):
        from fab_bundle.generators.templates import init_from_template
        output = tmp_path / "osdu-test"
        init_from_template("osdu_analytics", output, {"project_name": "osdu-test"})

        assert (output / "fabric.yml").exists()
        assert (output / "notebooks" / "ingest_osdu_entities.py").exists()
        assert (output / "notebooks" / "flatten_wells.py").exists()
        assert (output / "sql" / "create_well_views.sql").exists()
        assert (output / "agent" / "instructions.md").exists()
        assert (output / "agent" / "examples.yaml").exists()
