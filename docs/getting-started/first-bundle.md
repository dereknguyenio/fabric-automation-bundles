# Your First Bundle

A minimal `fabric.yml`:

```yaml
bundle:
  name: hello-fabric
  version: "1.0.0"

workspace:
  capacity_id: "your-capacity-guid"

resources:
  lakehouses:
    my_lakehouse:
      description: "My first lakehouse"

  notebooks:
    hello_notebook:
      path: ./notebooks/hello.py
      description: "Hello world notebook"

targets:
  dev:
    default: true
    workspace:
      name: hello-fabric-dev
```

Create the notebook:

```bash
mkdir notebooks
echo '# Hello from Fabric Automation Bundles
print("It works!")' > notebooks/hello.py
```

Deploy:

```bash
fab-bundle validate
fab-bundle deploy --target dev
```
