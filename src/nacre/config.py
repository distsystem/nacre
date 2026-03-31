"""Configuration models and loaders for branch materialization."""

import pathlib
from typing import Any

import pydantic
import pydantic_settings
import yaml


class LayerSettings(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid", frozen=True)

    head: pydantic.StrictStr
    base: pydantic.StrictStr | None = None
    name: pydantic.StrictStr | None = None


class NacreSettings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(extra="forbid", frozen=True)

    repo: pathlib.Path
    target_branch: pydantic.StrictStr
    base_ref: pydantic.StrictStr
    fetch: list[pydantic.StrictStr] = pydantic.Field(default_factory=list)
    layers: list[LayerSettings] = pydantic.Field(default_factory=list)


def load_config_data(config_path: pathlib.Path) -> dict[str, Any]:
    raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if raw_data is None:
        return {}
    if not isinstance(raw_data, dict):
        raise TypeError("YAML config must contain a mapping at the top level")

    data = dict(raw_data)
    resolve_repo_path(config_path, data)
    return data


def resolve_repo_path(config_path: pathlib.Path, data: dict[str, Any]) -> None:
    repo = data.get("repo")
    if not isinstance(repo, str):
        return

    repo_path = pathlib.Path(repo).expanduser()
    if not repo_path.is_absolute():
        repo_path = config_path.parent / repo_path
    data["repo"] = repo_path.resolve()


def load_settings(config_path: pathlib.Path) -> NacreSettings:
    resolved_path = config_path.resolve()
    return NacreSettings.model_validate(load_config_data(resolved_path))
