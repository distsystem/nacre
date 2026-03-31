import pathlib

import pytest

from branch_materializer.config import load_spec


def test_load_spec_resolves_repo_relative_to_config(tmp_path):
    repo_dir = tmp_path / "repos" / "target"
    repo_dir.mkdir(parents=True)
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "branch.toml"
    config_path.write_text(
        'repo = "../repos/target"\n'
        'target_branch = "dev"\n'
        'base_ref = "upstream/main"\n'
        'fetch = ["upstream"]\n'
        '\n'
        '[[layer]]\n'
        'head = "origin/topic"\n'
        'base = "upstream/main"\n'
        'name = "topic"\n'
    )

    spec = load_spec(config_path)

    assert spec.repo == repo_dir.resolve()
    assert spec.target_branch == "dev"
    assert spec.base_ref == "upstream/main"
    assert spec.fetch == ["upstream"]
    assert spec.layers[0].head == "origin/topic"
    assert spec.layers[0].base == "upstream/main"
    assert spec.layers[0].name == "topic"


def test_load_spec_rejects_missing_repo(tmp_path):
    config_path = tmp_path / "branch.toml"
    config_path.write_text('target_branch = "dev"\nbase_ref = "main"\n')

    with pytest.raises(ValueError, match="config field 'repo' must be a string"):
        load_spec(config_path)


def test_load_spec_rejects_non_string_layer_head(tmp_path):
    config_path = tmp_path / "branch.toml"
    config_path.write_text(
        'repo = "."\n'
        'target_branch = "dev"\n'
        'base_ref = "main"\n'
        '\n'
        '[[layer]]\n'
        'head = 1\n'
    )

    with pytest.raises(ValueError, match="layer #1 field 'head' must be a string"):
        load_spec(config_path)
