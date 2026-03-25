"""
Template engine — generates new bundle projects from templates.

Supports built-in templates and custom templates from Git repos or local paths.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader
from rich.console import Console


TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def list_templates() -> list[dict[str, str]]:
    """List available built-in templates."""
    templates = []
    if TEMPLATES_DIR.exists():
        for template_dir in sorted(TEMPLATES_DIR.iterdir()):
            if template_dir.is_dir():
                meta_file = template_dir / "template.yml"
                meta: dict[str, str] = {"name": template_dir.name}
                if meta_file.exists():
                    with open(meta_file) as f:
                        meta.update(yaml.safe_load(f) or {})
                templates.append(meta)
    return templates


def init_from_template(
    template_name: str,
    output_dir: Path,
    variables: dict[str, str] | None = None,
    console: Console | None = None,
) -> Path:
    """
    Initialize a new bundle project from a template.

    Args:
        template_name: Name of a built-in template or path to custom template.
        output_dir: Directory to create the project in.
        variables: Template variables to substitute.
        console: Rich console for output.

    Returns:
        Path to the created fabric.yml.
    """
    console = console or Console()
    variables = variables or {}

    # Support URL-based templates
    if template_name.startswith("http://") or template_name.startswith("https://"):
        import tempfile
        import urllib.request
        import tarfile
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "template.tar.gz"
            urllib.request.urlretrieve(template_name, archive_path)
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(tmpdir, filter="data")
            # Find template.yml in extracted content
            for p in Path(tmpdir).rglob("template.yml"):
                template_dir = p.parent
                break
            else:
                raise ValueError(f"No template.yml found in downloaded archive")
            # Copy to output
            if output_dir.exists():
                shutil.rmtree(output_dir)
            shutil.copytree(template_dir, output_dir, dirs_exist_ok=True)
            if console:
                console.print(f"[green]Created project from URL template at {output_dir}[/green]")
            return

    # Support github: shorthand
    if template_name.startswith("github:"):
        repo = template_name.replace("github:", "")
        template_name = f"https://github.com/{repo}/archive/refs/heads/main.tar.gz"
        return init_from_template(template_name, output_dir, variables, console)

    # Resolve template directory
    template_dir = TEMPLATES_DIR / template_name
    if not template_dir.exists():
        # Try as a path
        template_dir = Path(template_name)
        if not template_dir.exists():
            available = [t["name"] for t in list_templates()]
            raise ValueError(
                f"Template '{template_name}' not found.\n"
                f"Available templates: {', '.join(available) or 'none'}\n"
                f"Install templates or provide a path to a custom template directory."
            )

    # Read template metadata
    meta_file = template_dir / "template.yml"
    meta: dict[str, Any] = {}
    if meta_file.exists():
        with open(meta_file) as f:
            meta = yaml.safe_load(f) or {}

    console.print(f"Initializing from template: [bold]{meta.get('name', template_name)}[/bold]")
    if meta.get("description"):
        console.print(f"  {meta['description']}")

    # Set default variables
    defaults = meta.get("variables", {})
    for key, info in defaults.items():
        if key not in variables:
            if isinstance(info, dict):
                variables[key] = info.get("default", "")
            else:
                variables[key] = str(info)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Set up Jinja2
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        keep_trailing_newline=True,
        variable_start_string="${{",
        variable_end_string="}}",
    )

    # Process template files
    files_created = 0
    for src_path in sorted(template_dir.rglob("*")):
        if src_path.is_file() and src_path.name != "template.yml":
            relative = src_path.relative_to(template_dir)
            dest_path = output_dir / relative
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Render Jinja2 templates
            if src_path.suffix in (".yml", ".yaml", ".py", ".md", ".txt", ".json", ".sql", ".kql"):
                try:
                    template = env.get_template(str(relative))
                    content = template.render(**variables)
                    dest_path.write_text(content, encoding="utf-8")
                except Exception:
                    # If template rendering fails, copy as-is
                    shutil.copy2(src_path, dest_path)
            else:
                shutil.copy2(src_path, dest_path)

            files_created += 1

    console.print(f"  Created {files_created} files in {output_dir}")
    console.print()
    console.print("[bold green]Project initialized.[/bold green]")
    console.print()
    console.print("Next steps:")
    console.print(f"  cd {output_dir}")
    console.print("  # Edit fabric.yml to match your environment")
    console.print("  fab bundle validate")
    console.print("  fab bundle plan")
    console.print("  fab bundle deploy")

    return output_dir / "fabric.yml"
