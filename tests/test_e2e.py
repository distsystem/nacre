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
    # Source repo with stacked branches
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-b", "main")
    git(src, "config", "user.name", "Test")
    git(src, "config", "user.email", "test@test.com")
    commit(src, "base.txt", "base\n", "base")

    git(src, "checkout", "-b", "feature")
    commit(src, "feature.txt", "feature\n", "add feature")

    git(src, "checkout", "-b", "patch")
    commit(src, "patch.txt", "patch\n", "local patch")
    git(src, "checkout", "main")

    # Bare repos acting as GitHub remotes
    upstream_bare = tmp_path / "upstream.git"
    git(tmp_path, "clone", "--bare", str(src), str(upstream_bare))

    fork_bare = tmp_path / "fork.git"
    git(tmp_path, "clone", "--bare", str(src), str(fork_bare))

    # Working repo (user's local clone)
    repo = tmp_path / "repo"
    git(tmp_path, "clone", str(upstream_bare), str(repo))
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@test.com")
    git(repo, "remote", "rename", "origin", "upstream-org")
    git(repo, "remote", "add", "contributor", str(fork_bare))

    config = tmp_path / "nacre.yaml"
    config.write_text(
        f"upstream: upstream-org/testrepo:main\n"
        f"target: dev\n"
        f"dir: {repo}\n"
        f"layers:\n"
        f"  - contributor/testrepo:feature\n"
        f"  - contributor/testrepo:patch\n"
    )

    monkeypatch.setattr(sys, "argv", ["nacre", str(config)])
    nacre.cli.main()

    subjects = git(repo, "log", "--format=%s", "dev").splitlines()
    assert subjects == ["local patch", "add feature", "base"]
