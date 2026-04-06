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
