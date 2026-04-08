# nacre

Materialize declared Git branches from a declarative repository spec.

## Usage

Place a `nacre.yaml` in your project directory, then run:

```bash
nacre
```

Fields can be overridden via CLI args or env vars (`NACRE_` prefix):

```bash
nacre --checkout staging
NACRE_CHECKOUT=staging nacre
```

## Config

```yaml
repo:
  dir: ../python/jupyverse/jupyverse
  remotes:
    upstream:
      github: jupyter-server/jupyverse
    my_fork:
      github: my-fork/jupyverse
    other:
      github: other-person/jupyverse

checkout: patch_on_fix

branches:
  main: upstream:main
  fix_federated: my_fork:fix/federated-extensions-symlink@main
  some_feature: other:some-feature@main
  patch_on_fix: my_fork:patch-on-fix@fix_federated
```

Each branch expression has one of two forms:

- `remote:branch`: mirror a remote branch into a local branch of the same declared name
- `remote:branch@base`: mirror the remote branch, then rebase it onto another declared branch

All declared remotes are added and fetched automatically before the declared branches are materialized, then `nacre` checks out the branch named by `checkout`.
