"""Main branch materialization workflow."""

import pathlib
import tempfile

import branch_materializer.config as config_module
import branch_materializer.git_ops as git_ops


def materialize_branch(settings: config_module.BranchMaterializerSettings) -> None:
    git_ops.ensure_git_repo(settings.repo)
    fetch_remotes(settings.repo, settings.fetch)
    checked_out_worktree = prepare_target_branch(settings.repo, settings.target_branch)
    final_commit = build_materialized_branch(settings)
    update_target_branch(
        settings.repo,
        settings.target_branch,
        checked_out_worktree,
        final_commit,
    )
    print(f"Updated {settings.target_branch} -> {final_commit}")


def fetch_remotes(repo: pathlib.Path, remotes: list[str]) -> None:
    for remote in remotes:
        git_ops.run_git(repo, "fetch", remote)


def prepare_target_branch(repo: pathlib.Path, target_branch: str) -> pathlib.Path | None:
    checked_out_worktree = git_ops.worktree_for_branch(repo, target_branch)
    if checked_out_worktree is not None:
        git_ops.ensure_clean_worktree(checked_out_worktree)
    return checked_out_worktree


def build_materialized_branch(
    settings: config_module.BranchMaterializerSettings,
) -> str:
    with tempfile.TemporaryDirectory(prefix="materialize-branch-") as temp_dir:
        temp_path = pathlib.Path(temp_dir)
        git_ops.run_git(
            settings.repo,
            "worktree",
            "add",
            "--detach",
            str(temp_path),
            settings.base_ref,
        )
        try:
            apply_layers(settings, temp_path)
            return git_ops.run_git(temp_path, "rev-parse", "HEAD")
        finally:
            git_ops.run_git(settings.repo, "worktree", "remove", "--force", str(temp_path))


def update_target_branch(
    repo: pathlib.Path,
    target_branch: str,
    checked_out_worktree: pathlib.Path | None,
    final_commit: str,
) -> None:
    if checked_out_worktree is not None:
        git_ops.run_git(checked_out_worktree, "reset", "--hard", final_commit)
        return

    git_ops.run_git(repo, "branch", "-f", target_branch, final_commit)


def apply_layers(
    settings: config_module.BranchMaterializerSettings,
    temp_path: pathlib.Path,
) -> None:
    previous_head = settings.base_ref
    for layer in settings.layers:
        layer_base = layer.base or previous_head
        git_ops.ensure_ancestor(settings.repo, layer_base, layer.head)
        commits = git_ops.rev_list_linear(settings.repo, layer_base, layer.head)
        if not commits:
            previous_head = layer.head
            continue
        label = layer.name or layer.head
        print(f"Applying {label}: {len(commits)} commit(s)")
        for commit in commits:
            git_ops.run_git(temp_path, "cherry-pick", commit)
        previous_head = layer.head
