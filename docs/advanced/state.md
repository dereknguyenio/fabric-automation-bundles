# State Management

Deployment state is stored in `.fab-bundle/` alongside your `fabric.yml`.

## State Files

- `state-{target}.json` — current deployed state per target
- `lock-{target}.json` — deployment lock
- `history/` — deployment history snapshots
- `audit.jsonl` — structured audit log
- `metrics.json` — deployment metrics

## Commands

```bash
fab-bundle status -t dev     # view current state
fab-bundle history -t dev    # view deploy history
fab-bundle rollback --last   # rollback to previous
```

Add `.fab-bundle/` to `.gitignore` — state is machine-specific.
