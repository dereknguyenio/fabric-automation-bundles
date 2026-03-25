# Contributing to Fabric Automation Bundles

Thank you for your interest in contributing. This project aims to bring Databricks Asset Bundles-style declarative project management to Microsoft Fabric.

## Development Setup

```bash
git clone https://github.com/microsoft/fabric-automation-bundles.git
cd fabric-automation-bundles
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest                      # Run all tests
pytest -v                   # Verbose output
pytest --cov=fab_bundle     # With coverage
```

## Code Quality

```bash
ruff check .                # Linting
black .                     # Formatting
mypy fab_bundle             # Type checking
```

## Adding a New Template

1. Create a directory under `fab_bundle/templates/your_template/`
2. Add a `template.yml` with metadata:
   ```yaml
   name: your-template
   description: "What this template does"
   variables:
     project_name:
       description: "Project name"
       default: "my-project"
   ```
3. Add a `fabric.yml` with `${{variable}}` placeholders
4. Add supporting files (notebooks, SQL, agent configs)
5. Add a test in `tests/test_bundle.py`

## Adding a New Resource Type

1. Add the Pydantic model in `fab_bundle/models/bundle.py`
2. Add it to `ResourcesConfig`
3. Add dependency rules in `fab_bundle/engine/resolver.py`
4. Add the Fabric API type mapping in `fab_bundle/providers/fabric_api.py`
5. Add deployment logic in `fab_bundle/engine/deployer.py`
6. Update the JSON Schema in `fabric.schema.json`
7. Add tests

## Pull Request Process

1. Fork the repo and create a branch
2. Make your changes
3. Run `pytest`, `ruff check .`, and `black --check .`
4. Submit a PR with a clear description

## Code of Conduct

This project follows the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
