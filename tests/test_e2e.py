"""End-to-end: set up a tmp repo, write config, run CLI, verify result."""

import pathlib
import subprocess
import sys

import nacre.cli


def git(cwd: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True,
    )
    return result.stdout.strip()


def commit(repo: pathlib.Path, name: str, content: str, message: str) -> str:
    (repo / name).write_text(content)
    git(repo, "add", name)
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def test_materialize_layers(tmp_path: pathlib.Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@test.com")
    commit(repo, "base.txt", "base\n", "base")

    git(repo, "checkout", "-b", "feature")
    feature = commit(repo, "feature.txt", "feature\n", "add feature")

    git(repo, "checkout", "main")
    git(repo, "checkout", "-b", "patch")
    git(repo, "cherry-pick", feature)
    patch = commit(repo, "patch.txt", "patch\n", "local patch")
    git(repo, "checkout", "main")

    config = tmp_path / "nacre.yaml"
    config.write_text(
        f"repo: {repo}\n"
        f"target_branch: dev\n"
        f"base_ref: main\n"
        f"layers:\n"
        f'  - name: feature\n'
        f'    head: "{feature}"\n'
        f'    base: main\n'
        f'  - name: patch\n'
        f'    head: "{patch}"\n'
        f'    base: "{feature}"\n'
    )

    monkeypatch.setattr(sys, "argv", ["nacre", str(config)])
    nacre.cli.main()

    subjects = git(repo, "log", "--format=%s", "dev").splitlines()
    assert subjects == ["local patch", "add feature", "base"]
