"""Repository materialization workflow and git operations."""

import pathlib
import subprocess

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


def _ensure_git_repo(
    repo: pathlib.Path,
    clone_remote_name: str,
    clone_remote_url: str,
) -> None:
    if repo.exists() and any(repo.iterdir()):
        try:
            _run_git(repo, "rev-parse", "--show-toplevel")
        except RuntimeError as exc:
            raise ValueError(f"not a git repository: {repo}") from exc
        return
    print(f"Cloning {clone_remote_url} into {repo}")
    repo.parent.mkdir(parents=True, exist_ok=True)
    _run_git(
        repo.parent,
        "clone",
        "-o",
        clone_remote_name,
        clone_remote_url,
        str(repo.resolve()),
    )


def _ensure_remote(repo: pathlib.Path, name: str, url: str) -> None:
    try:
        existing_url = _run_git(repo, "remote", "get-url", name)
    except RuntimeError:
        _run_git(repo, "remote", "add", name, url)
        return
    if existing_url != url:
        raise ValueError(
            f"remote {name!r} already points to {existing_url!r}, expected {url!r}"
        )


def materialize_repository(settings: config_module.NacreSettings) -> None:
    repo = settings.repo.dir
    branch_specs = settings.branch_specs()
    clone_remote_name, clone_remote = next(iter(settings.repo.remotes.items()))
    _ensure_git_repo(repo, clone_remote_name, clone_remote.fetch_url)
    _ensure_remotes(repo, settings.repo.remotes)
    _run_git(repo, "checkout", "--detach")
    for branch_name in settings.materialization_order():
        _materialize_branch(repo, branch_name, branch_specs[branch_name])
    _run_git(repo, "checkout", settings.checkout)
    final_commit = _run_git(repo, "rev-parse", settings.checkout)
    print(f"Checked out {settings.checkout} -> {final_commit}")


def _ensure_remotes(
    repo: pathlib.Path,
    remotes: dict[str, config_module.RemoteSpec],
) -> None:
    for remote_name, remote_spec in remotes.items():
        _ensure_remote(repo, remote_name, remote_spec.fetch_url)
        print(f"Fetching {remote_name}")
        _run_git(repo, "fetch", remote_name)


def _materialize_branch(
    repo: pathlib.Path,
    branch_name: str,
    branch_spec: config_module.BranchSpec,
) -> None:
    print(f"Updating {branch_name} from {branch_spec.source.tracking_ref}")
    _run_git(repo, "branch", "-f", branch_name, branch_spec.source.tracking_ref)
    _run_git(
        repo,
        "branch",
        "--set-upstream-to",
        branch_spec.source.tracking_ref,
        branch_name,
    )
    if branch_spec.base_branch is None:
        return

    _run_git(repo, "checkout", "-B", branch_name, branch_spec.source.tracking_ref)
    print(f"Rebasing {branch_name} onto {branch_spec.base_branch}")
    _run_git(repo, "rebase", branch_spec.base_branch)
    _run_git(
        repo,
        "branch",
        "--set-upstream-to",
        branch_spec.base_branch,
        branch_name,
    )
