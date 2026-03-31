"""Main branch materialization workflow."""

import pathlib
import tempfile

import nacre.config as config_module
import nacre.git_ops as git_ops


def materialize_branch(settings: config_module.NacreSettings) -> None:
    git_ops.ensure_git_repo(settings.dir)
    upstream = config_module.parse_remote_ref(settings.upstream)
    layer_refs = [config_module.parse_remote_ref(layer) for layer in settings.layers]
    ensure_remotes(settings.dir, [upstream, *layer_refs])
    checked_out_worktree = prepare_target_branch(settings.dir, settings.target)
    final_commit = build_materialized_branch(settings.dir, upstream, layer_refs)
    update_target_branch(
        settings.dir, settings.target, checked_out_worktree, final_commit,
    )
    print(f"Updated {settings.target} -> {final_commit}")


def ensure_remotes(
    repo: pathlib.Path, refs: list[config_module.RemoteRef],
) -> None:
    seen: set[str] = set()
    for ref in refs:
        if ref.remote_name in seen:
            continue
        seen.add(ref.remote_name)
        git_ops.ensure_remote(repo, ref.remote_name, ref.url)
        git_ops.run_git(repo, "fetch", ref.remote_name)


def prepare_target_branch(
    repo: pathlib.Path, target: str,
) -> pathlib.Path | None:
    checked_out_worktree = git_ops.worktree_for_branch(repo, target)
    if checked_out_worktree is not None:
        git_ops.ensure_clean_worktree(checked_out_worktree)
    return checked_out_worktree


def build_materialized_branch(
    repo: pathlib.Path,
    upstream: config_module.RemoteRef,
    layer_refs: list[config_module.RemoteRef],
) -> str:
    with tempfile.TemporaryDirectory(prefix="materialize-branch-") as temp_dir:
        temp_path = pathlib.Path(temp_dir)
        git_ops.run_git(
            repo, "worktree", "add", "--detach",
            str(temp_path), upstream.tracking_ref,
        )
        try:
            apply_layers(repo, upstream, layer_refs, temp_path)
            return git_ops.run_git(temp_path, "rev-parse", "HEAD")
        finally:
            git_ops.run_git(repo, "worktree", "remove", "--force", str(temp_path))


def update_target_branch(
    repo: pathlib.Path,
    target: str,
    checked_out_worktree: pathlib.Path | None,
    final_commit: str,
) -> None:
    if checked_out_worktree is not None:
        git_ops.run_git(checked_out_worktree, "reset", "--hard", final_commit)
        return
    git_ops.run_git(repo, "branch", "-f", target, final_commit)


def apply_layers(
    repo: pathlib.Path,
    upstream: config_module.RemoteRef,
    layer_refs: list[config_module.RemoteRef],
    temp_path: pathlib.Path,
) -> None:
    previous_ref = upstream.tracking_ref
    for ref in layer_refs:
        tracking = ref.tracking_ref
        git_ops.ensure_ancestor(repo, previous_ref, tracking)
        commits = git_ops.rev_list_linear(repo, previous_ref, tracking)
        if not commits:
            previous_ref = tracking
            continue
        label = f"{ref.owner}/{ref.repo}:{ref.branch}"
        print(f"Applying {label}: {len(commits)} commit(s)")
        for sha in commits:
            git_ops.run_git(temp_path, "cherry-pick", sha)
        previous_ref = tracking
