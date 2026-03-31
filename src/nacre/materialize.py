"""Branch materialization workflow and git operations."""

import pathlib
import subprocess
import tempfile

import nacre.config as config_module


def _run_git(cwd: pathlib.Path, *args: str) -> str:
    command = ["git", *args]
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        command_text = subprocess.list2cmdline(command)
        stderr = result.stderr.strip()
        raise RuntimeError(f"command failed in {cwd}: {command_text}\n{stderr}")
    return result.stdout.strip()


def _ensure_git_repo(repo: pathlib.Path) -> None:
    try:
        _run_git(repo, "rev-parse", "--show-toplevel")
    except RuntimeError as exc:
        raise ValueError(f"not a git repository: {repo}") from exc


def _ensure_remote(repo: pathlib.Path, name: str, url: str) -> None:
    try:
        _run_git(repo, "remote", "get-url", name)
    except RuntimeError:
        _run_git(repo, "remote", "add", name, url)


def _worktree_for_branch(repo: pathlib.Path, branch: str) -> pathlib.Path | None:
    branch_ref = f"refs/heads/{branch}"
    output = _run_git(repo, "worktree", "list", "--porcelain")
    current_worktree: pathlib.Path | None = None
    for line in output.splitlines():
        if line.startswith("worktree "):
            current_worktree = pathlib.Path(line.removeprefix("worktree "))
            continue
        if line.startswith("branch ") and line.removeprefix("branch ") == branch_ref:
            return current_worktree
    return None


def _ensure_clean_worktree(worktree: pathlib.Path) -> None:
    status = _run_git(worktree, "status", "--short")
    if status:
        raise RuntimeError(
            f"target branch is checked out in {worktree} and has uncommitted changes"
        )


def _ensure_ancestor(repo: pathlib.Path, base: str, head: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, head],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"layer base {base!r} is not an ancestor of {head!r}")


def _rev_list_linear(repo: pathlib.Path, base: str, head: str) -> list[str]:
    output = _run_git(
        repo,
        "rev-list",
        "--reverse",
        "--topo-order",
        "--parents",
        f"{base}..{head}",
    )
    commits: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        parts = line.split()
        commit = parts[0]
        if len(parts) > 2:
            raise RuntimeError(
                f"merge commit {commit} is not supported; declare a linear layer instead"
            )
        commits.append(commit)
    return commits


# -- materialization workflow --


def materialize_branch(settings: config_module.NacreSettings) -> None:
    _ensure_git_repo(settings.dir)
    upstream = config_module.parse_remote_ref(settings.upstream)
    layer_refs = [config_module.parse_remote_ref(layer) for layer in settings.layers]
    _ensure_remotes(settings.dir, [upstream, *layer_refs])
    checked_out_worktree = _prepare_target_branch(settings.dir, settings.target)
    final_commit = _build_materialized_branch(settings.dir, upstream, layer_refs)
    _update_target_branch(
        settings.dir,
        settings.target,
        checked_out_worktree,
        final_commit,
    )
    print(f"Updated {settings.target} -> {final_commit}")


def _ensure_remotes(
    repo: pathlib.Path,
    refs: list[config_module.RemoteRef],
) -> None:
    seen: set[str] = set()
    for ref in refs:
        if ref.remote_name in seen:
            continue
        seen.add(ref.remote_name)
        _ensure_remote(repo, ref.remote_name, ref.url)
        _run_git(repo, "fetch", ref.remote_name)


def _prepare_target_branch(
    repo: pathlib.Path,
    target: str,
) -> pathlib.Path | None:
    checked_out_worktree = _worktree_for_branch(repo, target)
    if checked_out_worktree is not None:
        _ensure_clean_worktree(checked_out_worktree)
    return checked_out_worktree


def _build_materialized_branch(
    repo: pathlib.Path,
    upstream: config_module.RemoteRef,
    layer_refs: list[config_module.RemoteRef],
) -> str:
    with tempfile.TemporaryDirectory(prefix="materialize-branch-") as temp_dir:
        temp_path = pathlib.Path(temp_dir)
        _run_git(
            repo,
            "worktree",
            "add",
            "--detach",
            str(temp_path),
            upstream.tracking_ref,
        )
        try:
            _apply_layers(repo, upstream, layer_refs, temp_path)
            return _run_git(temp_path, "rev-parse", "HEAD")
        finally:
            _run_git(repo, "worktree", "remove", "--force", str(temp_path))


def _update_target_branch(
    repo: pathlib.Path,
    target: str,
    checked_out_worktree: pathlib.Path | None,
    final_commit: str,
) -> None:
    if checked_out_worktree is not None:
        _run_git(checked_out_worktree, "reset", "--hard", final_commit)
        return
    _run_git(repo, "branch", "-f", target, final_commit)


def _apply_layers(
    repo: pathlib.Path,
    upstream: config_module.RemoteRef,
    layer_refs: list[config_module.RemoteRef],
    temp_path: pathlib.Path,
) -> None:
    previous_ref = upstream.tracking_ref
    for ref in layer_refs:
        tracking = ref.tracking_ref
        _ensure_ancestor(repo, previous_ref, tracking)
        commits = _rev_list_linear(repo, previous_ref, tracking)
        if not commits:
            previous_ref = tracking
            continue
        label = f"{ref.owner}/{ref.repo}:{ref.branch}"
        print(f"Applying {label}: {len(commits)} commit(s)")
        for sha in commits:
            _run_git(temp_path, "cherry-pick", sha)
        previous_ref = tracking
