"""
Dependency resolver — computes deployment order via topological sort.

Resources have implicit and explicit dependencies:
  - Notebooks depend on their environment and default_lakehouse
  - Pipelines depend on notebooks they reference
  - Reports depend on their semantic model
  - Semantic models depend on their default lakehouse
  - Data agents depend on their sources
  - Pipeline activities have explicit depends_on

The resolver builds a DAG and produces a deployment order.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from fab_bundle.models.bundle import BundleDefinition, ResourcesConfig


@dataclass
class ResourceNode:
    """A node in the dependency graph."""
    key: str
    resource_type: str
    depends_on: set[str] = field(default_factory=set)


class DependencyResolutionError(Exception):
    """Raised when dependencies cannot be resolved (e.g., cycles)."""


def build_dependency_graph(resources: ResourcesConfig) -> dict[str, ResourceNode]:
    """
    Build a dependency graph from resource definitions.

    Returns a dict of resource_key -> ResourceNode with dependencies populated.
    """
    nodes: dict[str, ResourceNode] = {}

    # Register all resources as nodes
    for type_name in type(resources).model_fields:
        resource_dict = getattr(resources, type_name)
        if isinstance(resource_dict, dict):
            for key in resource_dict:
                nodes[key] = ResourceNode(key=key, resource_type=type_name)

    # Environments have no dependencies (they're leaf nodes)

    # Lakehouses have no dependencies (they're leaf nodes)

    # Notebooks depend on environment + default_lakehouse
    for key, nb in resources.notebooks.items():
        if nb.environment and nb.environment in nodes:
            nodes[key].depends_on.add(nb.environment)
        if nb.default_lakehouse and nb.default_lakehouse in nodes:
            nodes[key].depends_on.add(nb.default_lakehouse)

    # Warehouses have no dependencies

    # Semantic models depend on default lakehouse
    for key, sm in resources.semantic_models.items():
        if sm.default_lakehouse and sm.default_lakehouse in nodes:
            nodes[key].depends_on.add(sm.default_lakehouse)

    # Reports depend on semantic model
    for key, report in resources.reports.items():
        if report.semantic_model and report.semantic_model in nodes:
            nodes[key].depends_on.add(report.semantic_model)

    # Pipelines depend on notebooks and other pipelines they reference
    for key, pipeline in resources.pipelines.items():
        for activity in pipeline.activities:
            if activity.notebook and activity.notebook in nodes:
                nodes[key].depends_on.add(activity.notebook)
            if activity.pipeline and activity.pipeline in nodes:
                nodes[key].depends_on.add(activity.pipeline)

    # Data agents depend on their sources
    for key, agent in resources.data_agents.items():
        for src in agent.sources:
            if src in nodes:
                nodes[key].depends_on.add(src)

    # Eventstreams can depend on eventhouses
    # (kept generic — no implicit deps for now)

    return nodes


def topological_sort(nodes: dict[str, ResourceNode]) -> list[ResourceNode]:
    """
    Topological sort of resource nodes (Kahn's algorithm).

    Returns nodes in deployment order (dependencies first).
    Raises DependencyResolutionError on cycles.
    """
    in_degree: dict[str, int] = defaultdict(int)
    for node in nodes.values():
        if node.key not in in_degree:
            in_degree[node.key] = 0
        for dep in node.depends_on:
            in_degree[node.key] += 1

    # Adjacency list (reversed: dep -> dependents)
    adj: dict[str, list[str]] = defaultdict(list)
    for node in nodes.values():
        for dep in node.depends_on:
            adj[dep].append(node.key)

    # Start with nodes that have no dependencies
    queue = sorted([k for k, deg in in_degree.items() if deg == 0])
    result: list[ResourceNode] = []

    while queue:
        current = queue.pop(0)
        if current in nodes:
            result.append(nodes[current])

        for dependent in sorted(adj.get(current, [])):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(result) < len(nodes):
        deployed_keys = {n.key for n in result}
        remaining = [k for k in nodes if k not in deployed_keys]
        raise DependencyResolutionError(
            f"Circular dependency detected involving: {remaining}\n"
            "Check your resource references for cycles."
        )

    return result


def get_deployment_order(bundle: BundleDefinition) -> list[ResourceNode]:
    """
    Get the full deployment order for a bundle.

    Returns resources sorted so dependencies are deployed first.
    """
    graph = build_dependency_graph(bundle.resources)
    return topological_sort(graph)


# Predefined deployment priority by resource type
# (used as secondary sort within the same dependency level)
RESOURCE_TYPE_PRIORITY = {
    "environments": 0,
    "lakehouses": 1,
    "eventhouses": 2,
    "warehouses": 3,
    "notebooks": 4,
    "semantic_models": 5,
    "reports": 6,
    "pipelines": 7,
    "eventstreams": 8,
    "data_agents": 9,
    "ml_experiments": 10,
    "ml_models": 11,
}


def get_deployment_waves(bundle: BundleDefinition) -> list[list[ResourceNode]]:
    """
    Group resources into deployment waves for parallel execution.

    Each wave contains resources whose dependencies are all satisfied
    by previous waves. Resources within a wave can be deployed in parallel.

    Returns:
        List of waves, where each wave is a list of ResourceNodes.
    """
    graph = build_dependency_graph(bundle.resources)

    # Compute in-degree (number of dependencies) and reverse adjacency list
    in_degree: dict[str, int] = {key: 0 for key in graph}
    dependents: dict[str, list[str]] = {key: [] for key in graph}

    for key, node in graph.items():
        valid_deps = [d for d in node.depends_on if d in graph]
        in_degree[key] = len(valid_deps)
        for dep in valid_deps:
            dependents[dep].append(key)

    waves: list[list[ResourceNode]] = []
    ready = [key for key, deg in in_degree.items() if deg == 0]

    while ready:
        wave = [graph[key] for key in sorted(ready)]
        waves.append(wave)

        next_ready: list[str] = []
        for key in ready:
            for dependent in dependents[key]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    next_ready.append(dependent)
        ready = next_ready

    return waves
