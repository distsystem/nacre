# nacre

Materialize a Git branch from a declarative YAML config.

## Usage

Place a `nacre.yaml` in your project directory, then run:

```bash
nacre
```

Fields can be overridden via CLI args or env vars (`NACRE_` prefix):

```bash
nacre --target staging
NACRE_TARGET=staging nacre
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
