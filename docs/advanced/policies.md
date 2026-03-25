# Policy Enforcement

```yaml
policies:
  require_description: true
  naming_convention: snake_case
  max_notebook_size_kb: 500
  blocked_libraries:
    - pandas<2.0
```

Policies are checked during `fab-bundle validate`.
