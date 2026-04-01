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

    monkeypatch.chdir(tmp_path)
    (tmp_path / "nacre.yaml").write_text(
        f"upstream: upstream-org/testrepo:main\n"
        f"target: dev\n"
        f"dir: repo\n"
        f"layers:\n"
        f"  - contributor/testrepo:feature\n"
        f"  - contributor/testrepo:patch\n"
    )

    monkeypatch.setattr(sys, "argv", ["nacre"])
    nacre.cli.main()

    subjects = git(repo, "log", "--format=%s", "dev").splitlines()
    assert subjects == ["local patch", "add feature", "base"]


def test_dir_auto_clone(tmp_path: pathlib.Path, monkeypatch) -> None:
    """dir that does not exist yet is cloned from upstream automatically."""
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-b", "main")
    git(src, "config", "user.name", "Test")
    git(src, "config", "user.email", "test@test.com")
    commit(src, "base.txt", "base\n", "base")

    git(src, "checkout", "-b", "feature")
    commit(src, "feature.txt", "feature\n", "add feature")
    git(src, "checkout", "main")

    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "--bare", str(src), str(bare))

    fork_bare = tmp_path / "fork.git"
    git(tmp_path, "clone", "--bare", str(src), str(fork_bare))

    repo = tmp_path / "repo"  # does not exist yet

    monkeypatch.chdir(tmp_path)
    # upstream URL points to local bare; nacre will clone it
    (tmp_path / "nacre.yaml").write_text(
        f"upstream: upstream-org/testrepo:main\n"
        f"target: dev\n"
        f"dir: repo\n"
        f"layers:\n"
        f"  - contributor/testrepo:feature\n"
    )

    # Patch RemoteRef.url to resolve to local bare repos
    import nacre.config as config_module
    _orig_url = config_module.RemoteRef.url.fget
    def _local_url(self):
        if self.owner == "upstream-org":
            return str(bare)
        if self.owner == "contributor":
            return str(fork_bare)
        return _orig_url(self)
    monkeypatch.setattr(config_module.RemoteRef, "url", property(_local_url))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@test.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@test.com")

    monkeypatch.setattr(sys, "argv", ["nacre"])
    nacre.cli.main()

    assert repo.exists()
    subjects = git(repo, "log", "--format=%s", "dev").splitlines()
    assert subjects == ["add feature", "base"]


def test_explicit_base(tmp_path: pathlib.Path, monkeypatch) -> None:
    """Two independent branches both based on main, applied with explicit base."""
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-b", "main")
    git(src, "config", "user.name", "Test")
    git(src, "config", "user.email", "test@test.com")
    commit(src, "base.txt", "base\n", "base")

    git(src, "checkout", "-b", "fix-a")
    commit(src, "a.txt", "a\n", "fix a")
    git(src, "checkout", "main")

    git(src, "checkout", "-b", "fix-b")
    commit(src, "b.txt", "b\n", "fix b")
    git(src, "checkout", "main")

    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "--bare", str(src), str(bare))

    repo = tmp_path / "repo"
    git(tmp_path, "clone", str(bare), str(repo))
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@test.com")
    git(repo, "remote", "rename", "origin", "upstream-org")

    monkeypatch.chdir(tmp_path)
    (tmp_path / "nacre.yaml").write_text(
        "upstream: upstream-org/testrepo:main\n"
        "target: dev\n"
        "dir: repo\n"
        "layers:\n"
        "  - upstream-org/testrepo:fix-a\n"
        "  - upstream-org/testrepo:main..upstream-org/testrepo:fix-b\n"
    )

    monkeypatch.setattr(sys, "argv", ["nacre"])
    nacre.cli.main()

    subjects = git(repo, "log", "--format=%s", "dev").splitlines()
    assert subjects == ["fix b", "fix a", "base"]
