"""Main branch materialization workflow."""

import pathlib
import tempfile

from branch_materializer.config import BranchSpec
from branch_materializer.git_ops import (
    ensure_ancestor,
    ensure_clean_worktree,
    ensure_git_repo,
    ensure_non_merge_commit,
    rev_list,
    run_git,
    worktree_for_branch,
)


def materialize_branch(spec: BranchSpec) -> None:
    ensure_git_repo(spec.repo)
    for remote in spec.fetch:
        run_git(spec.repo, "fetch", remote)

    checked_out_worktree = worktree_for_branch(spec.repo, spec.target_branch)
    if checked_out_worktree is not None:
        ensure_clean_worktree(checked_out_worktree)

    with tempfile.TemporaryDirectory(prefix="materialize-branch-") as temp_dir:
        temp_path = pathlib.Path(temp_dir)
        run_git(spec.repo, "worktree", "add", "--detach", str(temp_path), spec.base_ref)
        try:
            apply_layers(spec, temp_path)
            final_commit = run_git(temp_path, "rev-parse", "HEAD")
        finally:
            run_git(spec.repo, "worktree", "remove", "--force", str(temp_path))

    if checked_out_worktree is not None:
        run_git(checked_out_worktree, "reset", "--hard", final_commit)
    else:
        run_git(spec.repo, "branch", "-f", spec.target_branch, final_commit)

    print(f"Updated {spec.target_branch} -> {final_commit}")


def apply_layers(spec: BranchSpec, temp_path: pathlib.Path) -> None:
    previous_head = spec.base_ref
    for layer in spec.layers:
        layer_base = layer.base or previous_head
        ensure_ancestor(spec.repo, layer_base, layer.head)
        commits = rev_list(spec.repo, layer_base, layer.head)
        if not commits:
            previous_head = layer.head
            continue
        label = layer.name or layer.head
        print(f"Applying {label}: {len(commits)} commit(s)")
        for commit in commits:
            ensure_non_merge_commit(spec.repo, commit)
            run_git(temp_path, "cherry-pick", commit)
        previous_head = layer.head
