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
repo: ../python/jupyverse/jupyverse
target_branch: dev
base_ref: upstream/main
fetch:
  - upstream
  - origin
layers:
  - name: symlink fix
    head: origin/fix/federated-extensions-symlink
    base: upstream/main
  - name: local patches
    head: local-patches
    base: origin/fix/federated-extensions-symlink
```

Layers are replayed in order with `git cherry-pick` onto a temporary worktree created from `base_ref`.
