"""Branch materialization workflow and git operations."""

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


def _ensure_git_repo(repo: pathlib.Path, upstream: "config_module.RemoteRef") -> None:
    if repo.exists() and any(repo.iterdir()):
        try:
            _run_git(repo, "rev-parse", "--show-toplevel")
        except RuntimeError as exc:
            raise ValueError(f"not a git repository: {repo}") from exc
        return
    print(f"Cloning {upstream.url} into {repo}")
    repo.parent.mkdir(parents=True, exist_ok=True)
    _run_git(repo.parent, "clone", "-o", upstream.remote_name, upstream.url, str(repo.resolve()))


def _ensure_remote(repo: pathlib.Path, name: str, url: str) -> None:
    try:
        _run_git(repo, "remote", "get-url", name)
    except RuntimeError:
        _run_git(repo, "remote", "add", name, url)


# -- materialization workflow --


def materialize_branch(settings: config_module.NacreSettings) -> None:
    upstream = config_module.parse_remote_ref(settings.upstream)
    _ensure_git_repo(settings.dir, upstream)
    layers = [config_module.parse_layer(s) for s in settings.layers]
    all_refs = [upstream]
    for spec in layers:
        all_refs.append(spec.head)
        if spec.base is not None:
            all_refs.append(spec.base)
    _ensure_remotes(settings.dir, all_refs)
    _setup_local_branches(settings.dir, upstream, layers)
    _build_target_branch(settings.dir, settings.target, upstream, layers)
    final_commit = _run_git(settings.dir, "rev-parse", settings.target)
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
        print(f"Fetching {ref.remote_name}")
        _run_git(repo, "fetch", ref.remote_name)


def _setup_local_branches(
    repo: pathlib.Path,
    upstream: config_module.RemoteRef,
    layers: list[config_module.LayerSpec],
) -> None:
    _run_git(repo, "checkout", "--detach")
    _run_git(repo, "branch", "-f", upstream.branch, upstream.tracking_ref)
    for spec in layers:
        ref = spec.head
        _run_git(repo, "branch", "-f", ref.branch, ref.tracking_ref)


def _build_target_branch(
    repo: pathlib.Path,
    target: str,
    upstream: config_module.RemoteRef,
    layers: list[config_module.LayerSpec],
) -> None:
    _run_git(repo, "checkout", "-B", target, upstream.branch)
    for spec in layers:
        ref = spec.head
        label = f"{ref.owner}/{ref.repo}:{ref.branch}"
        print(f"Merging {label}")
        _run_git(repo, "merge", "--no-ff", "-m", f"Merge layer {label}", ref.branch)
