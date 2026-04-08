"""Configuration models and loaders for declarative repository materialization."""

import dataclasses
import pathlib
import re

import pydantic
import pydantic_settings

_GITHUB_REPO_RE = re.compile(r"^([^/:]+)/([^/:]+)$")
_BRANCH_EXPR_RE = re.compile(r"^([^:@]+):([^@]+?)(?:@([^@]+))?$")


@dataclasses.dataclass(frozen=True)
class RemoteBranchRef:
    remote: str
    branch: str

    @property
    def tracking_ref(self) -> str:
        return f"{self.remote}/{self.branch}"


@dataclasses.dataclass(frozen=True)
class BranchSpec:
    source: RemoteBranchRef
    base_branch: str | None = None

    @property
    def dependencies(self) -> list[str]:
        if self.base_branch is None:
            return []
        return [self.base_branch]


def build_github_url(repo_slug: str) -> str:
    match = _GITHUB_REPO_RE.fullmatch(repo_slug)
    if not match:
        raise ValueError(
            f"invalid GitHub repository {repo_slug!r}, expected 'owner/repo'"
        )
    owner, repo = match.groups()
    return f"https://github.com/{owner}/{repo}.git"


def parse_branch_expression(value: str) -> BranchSpec:
    match = _BRANCH_EXPR_RE.fullmatch(value)
    if not match:
        raise ValueError(
            f"invalid branch expression {value!r}, expected 'remote:branch' or "
            "'remote:branch@base'"
        )
    remote, branch, base_branch = match.groups()
    return BranchSpec(
        source=RemoteBranchRef(remote=remote, branch=branch),
        base_branch=base_branch,
    )


class RemoteSpec(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid", frozen=True)

    github: pydantic.StrictStr | None = pydantic.Field(
        default=None,
        description="GitHub repository in 'owner/repo' format",
        examples=["jupyter-server/jupyverse"],
    )
    url: pydantic.StrictStr | None = pydantic.Field(
        default=None,
        description="Clone URL for the remote repository",
        examples=["https://github.com/jupyter-server/jupyverse.git"],
    )

    @property
    def fetch_url(self) -> str:
        if self.url is not None:
            return self.url
        if self.github is None:
            raise RuntimeError("remote source is missing")
        return build_github_url(self.github)

    @pydantic.model_validator(mode="after")
    def validate_source(self) -> "RemoteSpec":
        source_count = int(self.github is not None) + int(self.url is not None)
        if source_count != 1:
            raise ValueError("remote must define exactly one of 'github' or 'url'")
        if self.github is not None:
            build_github_url(self.github)
        return self


class RepoSpec(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid", frozen=True)

    dir: pathlib.Path = pydantic.Field(
        default=pathlib.Path("."),
        description=(
            "Local repository directory managed by nacre. The repository is cloned "
            "automatically if it does not exist."
        ),
    )
    remotes: dict[str, RemoteSpec] = pydantic.Field(
        description=(
            "Named Git remotes used as the source of truth for declared branches. "
            "Every nacre run fetches these remotes before rebuilding declared "
            "branches."
        ),
        examples=[
            {
                "upstream": {"github": "jupyter-server/jupyverse"},
                "my_fork": {"github": "my-fork/jupyverse"},
            }
        ],
    )

    @pydantic.model_validator(mode="after")
    def validate_remotes(self) -> "RepoSpec":
        if not self.remotes:
            raise ValueError("repo.remotes must not be empty")
        return self


class NacreSettings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(
        extra="forbid",
        frozen=True,
        env_prefix="NACRE_",
        cli_parse_args=True,
        cli_prog_name="nacre",
        yaml_file="nacre.yaml",
    )

    repo: RepoSpec
    checkout: pydantic.StrictStr = pydantic.Field(
        description=(
            "Declared branch name to check out after all declared branches have "
            "been refreshed from their remote sources."
        ),
        examples=["dev"],
    )
    branches: dict[pydantic.StrictStr, pydantic.StrictStr] = pydantic.Field(
        description=(
            "Managed branch declarations. Each value must be 'remote:branch' or "
            "'remote:branch@base'. On every run, nacre resets each declared branch "
            "to its remote source and optionally rebases it onto the declared base. "
            "Remote branches are the source of truth: push local work before "
            "re-running nacre if you want to keep it. Use undeclared local branches "
            "for temporary scratch work."
        ),
        examples=[
            {
                "main": "upstream:main",
                "feature": "my_fork:feature@main",
            }
        ],
    )

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            pydantic_settings.YamlConfigSettingsSource(settings_cls),
        )

    def branch_specs(self) -> dict[str, BranchSpec]:
        return {
            branch_name: parse_branch_expression(branch_expr)
            for branch_name, branch_expr in self.branches.items()
        }

    def materialization_order(self) -> list[str]:
        branch_specs = self.branch_specs()
        order: list[str] = []
        visited: set[str] = set()

        def visit(branch_name: str) -> None:
            if branch_name in visited:
                return
            visited.add(branch_name)
            for dependency in branch_specs[branch_name].dependencies:
                visit(dependency)
            order.append(branch_name)

        for branch_name in self.branches:
            visit(branch_name)
        return order

    @pydantic.model_validator(mode="after")
    def validate_branch_graph(self) -> "NacreSettings":
        if self.checkout not in self.branches:
            raise ValueError(f"checkout branch {self.checkout!r} is not declared")

        branch_specs = self.branch_specs()
        for branch_name, branch_spec in branch_specs.items():
            if branch_spec.source.remote not in self.repo.remotes:
                raise ValueError(
                    f"branch {branch_name!r} references unknown remote "
                    f"{branch_spec.source.remote!r}"
                )
            if branch_spec.base_branch is None:
                continue
            if branch_spec.base_branch not in self.branches:
                raise ValueError(
                    f"branch {branch_name!r} references unknown branch "
                    f"{branch_spec.base_branch!r}"
                )
            if branch_spec.base_branch == branch_name:
                raise ValueError(
                    f"branch {branch_name!r} cannot depend on itself"
                )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(branch_name: str) -> None:
            if branch_name in visited:
                return
            if branch_name in visiting:
                raise ValueError(
                    f"branch graph contains a cycle at {branch_name!r}"
                )
            visiting.add(branch_name)
            for dependency in branch_specs[branch_name].dependencies:
                visit(dependency)
            visiting.remove(branch_name)
            visited.add(branch_name)

        for branch_name in self.branches:
            visit(branch_name)
        return self
