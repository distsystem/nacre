"""Configuration loading for declarative branch materialization."""

import dataclasses
import pathlib
import tomllib


@dataclasses.dataclass(frozen=True, slots=True)
class LayerSpec:
    head: str
    base: str | None = None
    name: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class BranchSpec:
    repo: pathlib.Path
    target_branch: str
    base_ref: str
    fetch: list[str]
    layers: list[LayerSpec]


def load_spec(config_path: pathlib.Path) -> BranchSpec:
    data = tomllib.loads(config_path.read_text())
    repo_value = data.get("repo")
    target_branch = data.get("target_branch")
    base_ref = data.get("base_ref")
    if not isinstance(repo_value, str):
        raise ValueError("config field 'repo' must be a string")
    if not isinstance(target_branch, str):
        raise ValueError("config field 'target_branch' must be a string")
    if not isinstance(base_ref, str):
        raise ValueError("config field 'base_ref' must be a string")

    fetch = data.get("fetch", [])
    if not isinstance(fetch, list) or any(not isinstance(item, str) for item in fetch):
        raise ValueError("config field 'fetch' must be a list of strings")

    layers_data = data.get("layer", [])
    if not isinstance(layers_data, list):
        raise ValueError("config field 'layer' must be an array of tables")

    layers: list[LayerSpec] = []
    for index, layer_data in enumerate(layers_data, start=1):
        if not isinstance(layer_data, dict):
            raise ValueError(f"layer #{index} must be a table")
        head = layer_data.get("head")
        if not isinstance(head, str):
            raise ValueError(f"layer #{index} field 'head' must be a string")
        base = layer_data.get("base")
        name = layer_data.get("name")
        if base is not None and not isinstance(base, str):
            raise ValueError(f"layer #{index} field 'base' must be a string")
        if name is not None and not isinstance(name, str):
            raise ValueError(f"layer #{index} field 'name' must be a string")
        layers.append(LayerSpec(head=head, base=base, name=name))

    repo_path = (config_path.parent / repo_value).resolve()
    return BranchSpec(
        repo=repo_path,
        target_branch=target_branch,
        base_ref=base_ref,
        fetch=fetch,
        layers=layers,
    )
