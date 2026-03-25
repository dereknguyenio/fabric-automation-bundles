# CI/CD Overview

Fabric Automation Bundles integrates into your CI/CD pipeline at every stage:

| Stage | Command | Purpose |
|-------|---------|---------|
| PR Check | `validate` | Catch errors before merge |
| PR Check | `plan` | Preview changes |
| Staging | `deploy -t staging -y` | Auto-deploy on merge |
| Production | `deploy -t prod -y` | Deploy after approval |
