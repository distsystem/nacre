# nacre

Materialize a Git branch from a declarative YAML config.

## Usage

```bash
pixi run env PYTHONPATH=src python -m nacre.cli /path/to/config.yaml
```

or after installation:

```bash
nacre /path/to/config.yaml
```

## Config

```yaml
upstream: jupyter-server/jupyverse:main
target: dev
dir: ../python/jupyverse/jupyverse
layers:
  - my-fork/jupyverse:fix/federated-extensions-symlink
  - other-person/jupyverse:some-feature
```

Each ref uses the `owner/repo:branch` format. Remotes are added and fetched automatically. Layers are cherry-picked in order onto a temporary worktree created from `upstream`.
