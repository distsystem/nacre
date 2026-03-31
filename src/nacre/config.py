"""Configuration models and loaders for branch materialization."""

import dataclasses
import pathlib
import re

import pydantic
import pydantic_settings


@dataclasses.dataclass(frozen=True)
class RemoteRef:
    owner: str
    repo: str
    branch: str

    @property
    def remote_name(self) -> str:
        return self.owner

    @property
    def tracking_ref(self) -> str:
        return f"{self.owner}/{self.branch}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}.git"


_REMOTE_REF_RE = re.compile(r"^([^/:]+)/([^/:]+):(.+)$")


def parse_remote_ref(value: str) -> RemoteRef:
    match = _REMOTE_REF_RE.fullmatch(value)
    if not match:
        raise ValueError(
            f"invalid ref format {value!r}, expected 'owner/repo:branch'"
        )
    return RemoteRef(owner=match.group(1), repo=match.group(2), branch=match.group(3))


class NacreSettings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(
        extra="forbid",
        frozen=True,
        env_prefix="NACRE_",
        cli_parse_args=True,
        cli_prog_name="nacre",
        yaml_file="nacre.yaml",
    )

    upstream: pydantic.StrictStr
    target: pydantic.StrictStr
    dir: pathlib.Path
    layers: list[pydantic.StrictStr] = pydantic.Field(default_factory=list)

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            pydantic_settings.YamlConfigSettingsSource(settings_cls),
        )

    @pydantic.model_validator(mode="after")
    def _validate_refs(self) -> "NacreSettings":
        all_refs = [parse_remote_ref(self.upstream)]
        for layer in self.layers:
            all_refs.append(parse_remote_ref(layer))
        remotes: dict[str, str] = {}
        for ref in all_refs:
            existing = remotes.get(ref.remote_name)
            if existing is not None and existing != ref.url:
                raise ValueError(
                    f"owner {ref.owner!r} maps to different repos: "
                    f"{existing} vs {ref.url}"
                )
            remotes[ref.remote_name] = ref.url
        return self
