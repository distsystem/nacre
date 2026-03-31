"""Tests for YAML settings loading."""

import pydantic
import pytest

import branch_materializer.config as config_module


def test_load_settings_resolves_repo_relative_to_config(tmp_path):
    repo_dir = tmp_path / "repos" / "target"
    repo_dir.mkdir(parents=True)
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "branch.yaml"
    config_path.write_text(
        "repo: ../repos/target\n"
        "target_branch: dev\n"
        "base_ref: upstream/main\n"
        "fetch:\n"
        "  - upstream\n"
        "layers:\n"
        "  - head: origin/topic\n"
        "    base: upstream/main\n"
        "    name: topic\n",
        encoding="utf-8",
    )

    settings = config_module.load_settings(config_path)

    assert settings.repo == repo_dir.resolve()
    assert settings.target_branch == "dev"
    assert settings.base_ref == "upstream/main"
    assert settings.fetch == ["upstream"]
    assert settings.layers[0].head == "origin/topic"
    assert settings.layers[0].base == "upstream/main"
    assert settings.layers[0].name == "topic"


def test_load_settings_rejects_missing_repo(tmp_path):
    config_path = tmp_path / "branch.yaml"
    config_path.write_text("target_branch: dev\nbase_ref: main\n", encoding="utf-8")

    with pytest.raises(pydantic.ValidationError) as exc_info:
        config_module.load_settings(config_path)

    assert any(
        error["loc"] == ("repo",) and error["type"] == "missing"
        for error in exc_info.value.errors(include_url=False)
    )


def test_load_settings_rejects_non_string_layer_head(tmp_path):
    config_path = tmp_path / "branch.yaml"
    config_path.write_text(
        "repo: .\n"
        "target_branch: dev\n"
        "base_ref: main\n"
        "layers:\n"
        "  - head: 1\n",
        encoding="utf-8",
    )

    with pytest.raises(pydantic.ValidationError) as exc_info:
        config_module.load_settings(config_path)

    assert any(
        error["loc"] == ("layers", 0, "head") and error["type"] == "string_type"
        for error in exc_info.value.errors(include_url=False)
    )


def test_load_settings_rejects_unknown_field(tmp_path):
    config_path = tmp_path / "branch.yaml"
    config_path.write_text(
        "repo: .\n"
        "target_branch: dev\n"
        "base_ref: main\n"
        "unknown: true\n",
        encoding="utf-8",
    )

    with pytest.raises(pydantic.ValidationError) as exc_info:
        config_module.load_settings(config_path)

    assert any(
        error["loc"] == ("unknown",) and error["type"] == "extra_forbidden"
        for error in exc_info.value.errors(include_url=False)
    )


def test_load_settings_rejects_empty_yaml(tmp_path):
    config_path = tmp_path / "branch.yaml"
    config_path.write_text("", encoding="utf-8")

    with pytest.raises(pydantic.ValidationError) as exc_info:
        config_module.load_settings(config_path)

    errors = exc_info.value.errors(include_url=False)
    assert any(error["loc"] == ("repo",) and error["type"] == "missing" for error in errors)
    assert any(
        error["loc"] == ("target_branch",) and error["type"] == "missing"
        for error in errors
    )
    assert any(
        error["loc"] == ("base_ref",) and error["type"] == "missing" for error in errors
    )


def test_load_settings_rejects_non_mapping_yaml(tmp_path):
    config_path = tmp_path / "branch.yaml"
    config_path.write_text("- repo: .\n", encoding="utf-8")

    with pytest.raises(TypeError, match="mapping at the top level"):
        config_module.load_settings(config_path)
