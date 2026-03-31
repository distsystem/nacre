"""Tests for the branch materialization workflow."""

import pathlib
import subprocess

import pytest

import branch_materializer.config as config_module
import branch_materializer.materialize as materialize_module


def git(cwd: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def make_commit(repo: pathlib.Path, path: str, content: str, message: str) -> str:
    file_path = repo / path
    file_path.write_text(content)
    git(repo, "add", path)
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def init_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    make_commit(repo, "base.txt", "base\n", "base")
    return repo


def test_materialize_branch_replays_layers_in_order(tmp_path):
    repo = init_repo(tmp_path)
    base = git(repo, "rev-parse", "HEAD")

    git(repo, "checkout", "-b", "topic")
    topic_head = make_commit(repo, "topic.txt", "topic\n", "topic")

    git(repo, "checkout", "main")
    git(repo, "checkout", "-b", "local-patches")
    git(repo, "cherry-pick", topic_head)
    local_head = make_commit(repo, "local.txt", "local\n", "local")
    git(repo, "checkout", "main")

    settings = config_module.BranchMaterializerSettings(
        repo=repo,
        target_branch="dev",
        base_ref="main",
        fetch=[],
        layers=[
            config_module.LayerSettings(head=topic_head, base=base, name="topic"),
            config_module.LayerSettings(head=local_head, base=topic_head, name="local"),
        ],
    )

    materialize_module.materialize_branch(settings)

    history = git(repo, "log", "--format=%s", "dev")
    assert history.splitlines()[:3] == ["local", "topic", "base"]


def test_materialize_branch_rejects_dirty_checked_out_target(tmp_path):
    repo = init_repo(tmp_path)
    git(repo, "checkout", "-b", "topic")
    head = make_commit(repo, "topic.txt", "topic\n", "topic")
    git(repo, "checkout", "main")
    git(repo, "checkout", "-b", "dev")
    (repo / "dirty.txt").write_text("dirty\n")

    settings = config_module.BranchMaterializerSettings(
        repo=repo,
        target_branch="dev",
        base_ref="main",
        fetch=[],
        layers=[config_module.LayerSettings(head=head, base="main")],
    )

    with pytest.raises(RuntimeError, match="has uncommitted changes"):
        materialize_module.materialize_branch(settings)


def test_materialize_branch_rejects_non_ancestor_layer_base(tmp_path):
    repo = init_repo(tmp_path)
    git(repo, "checkout", "-b", "topic")
    topic_head = make_commit(repo, "topic.txt", "topic\n", "topic")
    git(repo, "checkout", "main")
    other_head = make_commit(repo, "other.txt", "other\n", "other")

    settings = config_module.BranchMaterializerSettings(
        repo=repo,
        target_branch="dev",
        base_ref="main",
        fetch=[],
        layers=[config_module.LayerSettings(head=topic_head, base=other_head)],
    )

    with pytest.raises(RuntimeError, match="is not an ancestor"):
        materialize_module.materialize_branch(settings)


def test_materialize_branch_rejects_merge_commit_layer(tmp_path):
    repo = init_repo(tmp_path)
    git(repo, "checkout", "-b", "left")
    make_commit(repo, "left.txt", "left\n", "left")
    git(repo, "checkout", "main")
    git(repo, "checkout", "-b", "right")
    make_commit(repo, "right.txt", "right\n", "right")
    git(repo, "checkout", "left")
    git(repo, "merge", "--no-ff", "right", "-m", "merge")
    merge_head = git(repo, "rev-parse", "HEAD")
    base = git(repo, "merge-base", "main", merge_head)
    git(repo, "checkout", "main")

    settings = config_module.BranchMaterializerSettings(
        repo=repo,
        target_branch="dev",
        base_ref="main",
        fetch=[],
        layers=[config_module.LayerSettings(head=merge_head, base=base)],
    )

    with pytest.raises(RuntimeError, match="merge commit"):
        materialize_module.materialize_branch(settings)


def test_materialize_branch_updates_unchecked_target_branch(tmp_path):
    repo = init_repo(tmp_path)
    git(repo, "checkout", "-b", "topic")
    topic_head = make_commit(repo, "topic.txt", "topic\n", "topic")
    git(repo, "checkout", "main")

    settings = config_module.BranchMaterializerSettings(
        repo=repo,
        target_branch="dev",
        base_ref="main",
        fetch=[],
        layers=[config_module.LayerSettings(head=topic_head, base="main")],
    )

    materialize_module.materialize_branch(settings)

    history = git(repo, "log", "--format=%s", "dev")
    assert history.splitlines()[:2] == ["topic", "base"]
    assert git(repo, "branch", "--show-current") == "main"


def test_materialize_branch_removes_temporary_worktree_on_failure(tmp_path):
    repo = init_repo(tmp_path)
    git(repo, "checkout", "-b", "topic")
    topic_head = make_commit(repo, "topic.txt", "topic\n", "topic")
    git(repo, "checkout", "main")

    settings = config_module.BranchMaterializerSettings(
        repo=repo,
        target_branch="dev",
        base_ref="main",
        fetch=[],
        layers=[config_module.LayerSettings(head=topic_head, base="not-a-real-ref")],
    )

    with pytest.raises(RuntimeError, match="is not an ancestor"):
        materialize_module.materialize_branch(settings)

    worktrees = git(repo, "worktree", "list", "--porcelain")
    assert "materialize-branch-" not in worktrees
