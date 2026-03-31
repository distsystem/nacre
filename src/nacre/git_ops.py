"""Git subprocess helpers for branch materialization."""

import pathlib
import subprocess


def run_git(cwd: pathlib.Path, *args: str) -> str:
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


def ensure_git_repo(repo: pathlib.Path) -> None:
    try:
        run_git(repo, "rev-parse", "--show-toplevel")
    except RuntimeError as exc:
        raise ValueError(f"not a git repository: {repo}") from exc


def worktree_for_branch(repo: pathlib.Path, branch: str) -> pathlib.Path | None:
    branch_ref = f"refs/heads/{branch}"
    output = run_git(repo, "worktree", "list", "--porcelain")
    current_worktree: pathlib.Path | None = None
    for line in output.splitlines():
        if line.startswith("worktree "):
            current_worktree = pathlib.Path(line.removeprefix("worktree "))
            continue
        if line.startswith("branch ") and line.removeprefix("branch ") == branch_ref:
            return current_worktree
    return None


def ensure_clean_worktree(worktree: pathlib.Path) -> None:
    status = run_git(worktree, "status", "--short")
    if status:
        raise RuntimeError(
            f"target branch is checked out in {worktree} and has uncommitted changes"
        )


def ensure_ancestor(repo: pathlib.Path, base: str, head: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, head],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"layer base {base!r} is not an ancestor of {head!r}")


def rev_list_linear(repo: pathlib.Path, base: str, head: str) -> list[str]:
    output = run_git(
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
