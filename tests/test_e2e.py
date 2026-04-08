"""End-to-end: set up temporary repositories, run the CLI, verify results."""

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


def write_config(tmp_path: pathlib.Path, body: str) -> None:
    (tmp_path / "nacre.yaml").write_text(body)


def test_materialize_tracked_branch(tmp_path: pathlib.Path, monkeypatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-b", "main")
    git(src, "config", "user.name", "Test")
    git(src, "config", "user.email", "test@test.com")
    commit(src, "base.txt", "base\n", "base")
    git(src, "checkout", "-b", "feature")
    commit(src, "feature.txt", "feature\n", "add feature")
    git(src, "checkout", "main")

    upstream_bare = tmp_path / "upstream.git"
    git(tmp_path, "clone", "--bare", str(src), str(upstream_bare))

    repo = tmp_path / "repo"
    git(tmp_path, "clone", str(upstream_bare), str(repo))
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@test.com")
    git(repo, "remote", "rename", "origin", "upstream")

    monkeypatch.chdir(tmp_path)
    write_config(
        tmp_path,
        f"""repo:
  dir: repo
  remotes:
    upstream:
      url: {upstream_bare}
checkout: main
branches:
  main: upstream:main
  feature: upstream:feature@main
""",
    )

    monkeypatch.setattr(sys, "argv", ["nacre"])
    assert nacre.cli.main() == 0

    assert git(repo, "show", "main:base.txt") == "base"
    assert git(repo, "show", "feature:feature.txt") == "feature"
    assert git(repo, "rev-parse", "--abbrev-ref", "main@{upstream}") == "upstream/main"
    assert git(repo, "rev-parse", "--abbrev-ref", "feature@{upstream}") == "main"


def test_dir_auto_clone_and_rebase(tmp_path: pathlib.Path, monkeypatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-b", "main")
    git(src, "config", "user.name", "Test")
    git(src, "config", "user.email", "test@test.com")
    commit(src, "base.txt", "base\n", "base")

    git(src, "checkout", "-b", "feature")
    commit(src, "feature.txt", "feature\n", "add feature")
    git(src, "checkout", "main")
    commit(src, "main.txt", "advance\n", "advance main")

    upstream_bare = tmp_path / "upstream.git"
    git(tmp_path, "clone", "--bare", str(src), str(upstream_bare))

    fork_bare = tmp_path / "fork.git"
    git(tmp_path, "clone", "--bare", str(src), str(fork_bare))

    repo = tmp_path / "repo"

    monkeypatch.chdir(tmp_path)
    write_config(
        tmp_path,
        f"""repo:
  dir: repo
  remotes:
    upstream:
      url: {upstream_bare}
    contributor:
      url: {fork_bare}
checkout: feature
branches:
  main: upstream:main
  feature: contributor:feature@main
""",
    )

    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@test.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@test.com")
    monkeypatch.setattr(sys, "argv", ["nacre"])
    assert nacre.cli.main() == 0

    assert repo.exists()
    assert git(repo, "show", "feature:feature.txt") == "feature"
    assert git(repo, "show", "feature:main.txt") == "advance"
    assert git(repo, "merge-base", "feature", "main") == git(
        repo, "rev-parse", "main"
    )
    assert git(repo, "rev-parse", "--abbrev-ref", "feature@{upstream}") == "main"


def test_materialize_rebased_stack(tmp_path: pathlib.Path, monkeypatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-b", "main")
    git(src, "config", "user.name", "Test")
    git(src, "config", "user.email", "test@test.com")
    commit(src, "base.txt", "base\n", "base")

    git(src, "checkout", "-b", "feature")
    commit(src, "feature.txt", "feature\n", "add feature")

    git(src, "checkout", "-b", "patch")
    commit(src, "patch.txt", "patch\n", "add patch")
    git(src, "checkout", "main")
    commit(src, "main.txt", "advance\n", "advance main")

    upstream_bare = tmp_path / "upstream.git"
    git(tmp_path, "clone", "--bare", str(src), str(upstream_bare))

    fork_bare = tmp_path / "fork.git"
    git(tmp_path, "clone", "--bare", str(src), str(fork_bare))

    repo = tmp_path / "repo"
    git(tmp_path, "clone", str(upstream_bare), str(repo))
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@test.com")
    git(repo, "remote", "rename", "origin", "upstream")

    monkeypatch.chdir(tmp_path)
    write_config(
        tmp_path,
        f"""repo:
  dir: repo
  remotes:
    upstream:
      url: {upstream_bare}
    contributor:
      url: {fork_bare}
checkout: patch
branches:
  main: upstream:main
  feature: contributor:feature@main
  patch: contributor:patch@feature
""",
    )

    monkeypatch.setattr(sys, "argv", ["nacre"])
    assert nacre.cli.main() == 0

    assert git(repo, "show", "patch:feature.txt") == "feature"
    assert git(repo, "show", "patch:patch.txt") == "patch"
    assert git(repo, "show", "patch:main.txt") == "advance"
    assert git(repo, "merge-base", "patch", "feature") == git(
        repo, "rev-parse", "feature"
    )
    assert git(repo, "rev-parse", "--abbrev-ref", "patch@{upstream}") == "feature"
    assert git(repo, "log", "--format=%s", "patch").splitlines()[:4] == [
        "add patch",
        "add feature",
        "advance main",
        "base",
    ]


def test_repeat_run_refreshes_all_declared_branches(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-b", "main")
    git(src, "config", "user.name", "Test")
    git(src, "config", "user.email", "test@test.com")
    commit(src, "base.txt", "base\n", "base")

    git(src, "checkout", "-b", "feature")
    commit(src, "feature.txt", "feature v1\n", "add feature v1")

    git(src, "checkout", "-b", "patch")
    commit(src, "patch.txt", "patch v1\n", "add patch v1")
    git(src, "checkout", "main")
    commit(src, "main.txt", "main v1\n", "advance main v1")

    upstream_bare = tmp_path / "upstream.git"
    git(tmp_path, "clone", "--bare", str(src), str(upstream_bare))

    fork_bare = tmp_path / "fork.git"
    git(tmp_path, "clone", "--bare", str(src), str(fork_bare))

    git(src, "remote", "add", "upstream", str(upstream_bare))
    git(src, "remote", "add", "contributor", str(fork_bare))

    repo = tmp_path / "repo"
    git(tmp_path, "clone", str(upstream_bare), str(repo))
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@test.com")
    git(repo, "remote", "rename", "origin", "upstream")

    monkeypatch.chdir(tmp_path)
    write_config(
        tmp_path,
        f"""repo:
  dir: repo
  remotes:
    upstream:
      url: {upstream_bare}
    contributor:
      url: {fork_bare}
checkout: patch
branches:
  main: upstream:main
  feature: contributor:feature@main
  patch: contributor:patch@feature
""",
    )

    monkeypatch.setattr(sys, "argv", ["nacre"])
    assert nacre.cli.main() == 0

    git(src, "checkout", "main")
    commit(src, "main.txt", "main v2\n", "advance main v2")
    git(src, "push", "upstream", "main")

    git(src, "checkout", "feature")
    commit(src, "feature.txt", "feature v2\n", "advance feature v2")
    git(src, "push", "contributor", "feature")

    git(src, "checkout", "patch")
    commit(src, "patch.txt", "patch v2\n", "advance patch v2")
    git(src, "push", "contributor", "patch")

    assert nacre.cli.main() == 0

    assert git(repo, "show", "main:main.txt") == "main v2"
    assert git(repo, "show", "feature:main.txt") == "main v2"
    assert git(repo, "show", "feature:feature.txt") == "feature v2"
    assert git(repo, "show", "patch:main.txt") == "main v2"
    assert git(repo, "show", "patch:feature.txt") == "feature v2"
    assert git(repo, "show", "patch:patch.txt") == "patch v2"
    assert git(repo, "merge-base", "feature", "main") == git(
        repo, "rev-parse", "main"
    )
    assert git(repo, "merge-base", "patch", "feature") == git(
        repo, "rev-parse", "feature"
    )
