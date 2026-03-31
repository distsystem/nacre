"""Configuration models and loaders for branch materialization."""

import pathlib
from typing import Any, ClassVar

import pydantic
import pydantic_settings
import yaml


class LayerSettings(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid", frozen=True)

    head: pydantic.StrictStr
    base: pydantic.StrictStr | None = None
    name: pydantic.StrictStr | None = None


class YamlFileSettingsSource(pydantic_settings.PydanticBaseSettingsSource):
    def __init__(
        self,
        settings_cls: type[pydantic_settings.BaseSettings],
        config_path: pathlib.Path,
    ) -> None:
        super().__init__(settings_cls)
        self.config_path = config_path
        self.data = self.load_data()

    def load_data(self) -> dict[str, Any]:
        raw_data = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        if raw_data is None:
            return {}
        if not isinstance(raw_data, dict):
            raise TypeError("YAML config must contain a mapping at the top level")

        data = dict(raw_data)
        self.resolve_repo_path(data)
        return data

    def resolve_repo_path(self, data: dict[str, Any]) -> None:
        repo = data.get("repo")
        if not isinstance(repo, str):
            return

        repo_path = pathlib.Path(repo).expanduser()
        if not repo_path.is_absolute():
            repo_path = self.config_path.parent / repo_path
        data["repo"] = repo_path.resolve()

    def get_field_value(
        self,
        field: Any,
        field_name: str,
    ) -> tuple[Any, str, bool]:
        value = self.data.get(field_name)
        return value, field_name, False

    def prepare_field_value(
        self,
        field_name: str,
        field: Any,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        return value

    def __call__(self) -> dict[str, Any]:
        return dict(self.data)


class BranchMaterializerSettings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(extra="forbid", frozen=True)

    _config_path: ClassVar[pathlib.Path | None] = None

    repo: pathlib.Path
    target_branch: pydantic.StrictStr
    base_ref: pydantic.StrictStr
    fetch: list[pydantic.StrictStr] = pydantic.Field(default_factory=list)
    layers: list[LayerSettings] = pydantic.Field(default_factory=list)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[pydantic_settings.BaseSettings],
        init_settings: pydantic_settings.PydanticBaseSettingsSource,
        env_settings: pydantic_settings.PydanticBaseSettingsSource,
        dotenv_settings: pydantic_settings.PydanticBaseSettingsSource,
        file_secret_settings: pydantic_settings.PydanticBaseSettingsSource,
    ) -> tuple[pydantic_settings.PydanticBaseSettingsSource, ...]:
        if cls._config_path is None:
            return (init_settings,)

        return (init_settings, YamlFileSettingsSource(settings_cls, cls._config_path))


def load_settings(config_path: pathlib.Path) -> BranchMaterializerSettings:
    resolved_path = config_path.resolve()

    class FileBackedBranchMaterializerSettings(BranchMaterializerSettings):
        _config_path = resolved_path

    return FileBackedBranchMaterializerSettings()
