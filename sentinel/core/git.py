import subprocess


def get_staged_diff() -> str:
    result = subprocess.run(
        ["git", "diff", "--staged", "--unified=3", "--", "*.py"],
        capture_output=True, text=True,
    )
    return result.stdout


def get_staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--staged", "--name-only", "--", "*.py"],
        capture_output=True, text=True,
    )
    return [f for f in result.stdout.strip().splitlines() if f]


def get_branch_diff(base_branch: str = "main") -> tuple[str, list[str]]:
    """Return (diff_text, changed_files) comparing current branch to base."""
    diff = subprocess.run(
        ["git", "diff", f"{base_branch}...HEAD", "--unified=3", "--", "*.py"],
        capture_output=True, text=True,
    ).stdout
    files = subprocess.run(
        ["git", "diff", f"{base_branch}...HEAD", "--name-only", "--", "*.py"],
        capture_output=True, text=True,
    ).stdout
    return diff, [f for f in files.strip().splitlines() if f]


def get_current_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() or "HEAD"
