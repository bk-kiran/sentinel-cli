import re
import sys
from datetime import datetime
import typer
from rich.console import Console
from rich.rule import Rule
from pathlib import Path

from sentinel.core.config import load_config, SentinelConfig
from sentinel.core.git import get_staged_diff, get_staged_files, get_branch_diff, get_current_branch
from sentinel.core.parser import build_call_graph, extract_edited_functions
from sentinel.core.runner import run_agents

app = typer.Typer(
    name="sentinel",
    help="Agentic pre-commit code guardian for Python projects.",
    add_completion=False,
)
console = Console()


@app.command()
def check(
    file: Path = typer.Option(None, "--file", "-f", help="Check a specific file instead of staged changes."),
    strict: bool = typer.Option(False, "--strict", "-s", help="Exit with error code if any issues found."),
):
    """Analyze staged changes with three specialized AI agents."""
    config = load_config()

    if file:
        if not file.exists():
            console.print(f"[red]File not found:[/red] {file}")
            raise typer.Exit(1)
        diff = file.read_text()
        changed_files = [str(file)]
    else:
        diff = get_staged_diff()
        changed_files = get_staged_files()

    if not diff.strip():
        console.print("[yellow]No staged changes found.[/yellow] Stage some files with `git add` first.")
        raise typer.Exit(0)

    # Filter out ignored paths
    if config.ignore.paths:
        changed_files = [
            f for f in changed_files
            if not any(f.startswith(p) for p in config.ignore.paths)
        ]

    files_str = "  ".join(changed_files) if changed_files else "(all files ignored)"
    console.print()
    console.print(Rule(f"[bold cyan]sentinel[/bold cyan]  [dim]{files_str}[/dim]"))
    console.print()

    call_graph = build_call_graph(Path("."))
    edited_functions = extract_edited_functions(diff)

    # Filter out ignored functions before blast radius analysis
    if config.ignore.functions:
        edited_functions = [f for f in edited_functions if f not in config.ignore.functions]

    enabled_agents = {
        name for name, enabled in [
            ("readability", config.agents.readability),
            ("dead_code", config.agents.dead_code),
            ("blast_radius", config.agents.blast_radius),
        ]
        if enabled
    }

    results = run_agents(
        diff=diff,
        call_graph=call_graph,
        edited_functions=edited_functions,
        enabled_agents=enabled_agents,
        blast_radius_max_depth=config.blast_radius.max_depth,
    )

    should_block = _render_results(results, changed_files, config)

    if should_block or (strict and any(results[k] for k in results)):
        raise typer.Exit(1)


@app.command()
def report(
    base: str = typer.Option(None, "--base", "-b", help="Base branch to diff against."),
    output: str = typer.Option("sentinel-report.md", "--output", "-o", help="Output file, or - for stdout."),
):
    """Analyze the full branch diff and generate a markdown PR review document."""
    config = load_config()
    base_branch = base or config.report.base_branch

    diff, changed_files = get_branch_diff(base_branch)

    if not diff.strip():
        console.print(f"[yellow]No Python changes found between current branch and {base_branch}.[/yellow]")
        raise typer.Exit(0)

    if config.ignore.paths:
        changed_files = [
            f for f in changed_files
            if not any(f.startswith(p) for p in config.ignore.paths)
        ]

    if output != "-":
        console.print()
        console.print(Rule(f"[bold cyan]sentinel report[/bold cyan]  [dim]vs {base_branch}[/dim]"))
        console.print()

    call_graph = build_call_graph(Path("."))
    edited_functions = extract_edited_functions(diff)

    if config.ignore.functions:
        edited_functions = [f for f in edited_functions if f not in config.ignore.functions]

    enabled_agents = {
        name for name, enabled in [
            ("readability", config.agents.readability),
            ("dead_code", config.agents.dead_code),
            ("blast_radius", config.agents.blast_radius),
        ]
        if enabled
    }

    results = run_agents(
        diff=diff,
        call_graph=call_graph,
        edited_functions=edited_functions,
        enabled_agents=enabled_agents,
        blast_radius_max_depth=config.blast_radius.max_depth,
    )

    branch = get_current_branch()
    markdown = _build_report(results, changed_files, branch, base_branch, config)

    if output == "-":
        print(markdown)
    else:
        Path(output).write_text(markdown)
        console.print(f"[green]✔[/green] Report written to [bold]{output}[/bold]")


@app.command()
def install():
    """Install sentinel as a git pre-commit hook in this repo."""
    hook_path = Path(".git/hooks/pre-commit")

    if not Path(".git").exists():
        console.print("[red]Not a git repository.[/red] Run this from your project root.")
        raise typer.Exit(1)

    hook_script = "#!/bin/sh\nsentinel check --strict\n"

    if hook_path.exists():
        console.print("[yellow]Pre-commit hook already exists.[/yellow] Overwrite? [y/N] ", end="")
        if input().strip().lower() != "y":
            raise typer.Exit(0)

    hook_path.write_text(hook_script)
    hook_path.chmod(0o755)
    console.print("[green]✔[/green] sentinel installed as pre-commit hook.")


@app.command()
def uninstall():
    """Remove the sentinel pre-commit hook."""
    hook_path = Path(".git/hooks/pre-commit")
    if hook_path.exists():
        hook_path.unlink()
        console.print("[green]✔[/green] sentinel hook removed.")
    else:
        console.print("[yellow]No pre-commit hook found.[/yellow]")


def _render_results(results: dict, changed_files: list[str], config: SentinelConfig) -> bool:
    """
    Print per-section results. Returns True if any error-severity section
    has findings (caller should exit 1).
    """
    sections = [
        ("readability",  "Readability",  "yellow"),
        ("dead_code",    "Dead Code",    "magenta"),
        ("blast_radius", "Blast Radius", "red"),
    ]

    issue_counts: dict[str, int] = {}
    should_block: bool = False

    for key, label, color in sections:
        items: list[str] = results.get(key, [])
        severity: str = getattr(config.severity, key, "warning")
        severity_tag = "[red]error[/red]" if severity == "error" else "[yellow]warn[/yellow]"

        if not items:
            console.print(f"[green]✔[/green]  [bold]{label}[/bold]")
        else:
            issue_counts[key] = len(items)
            if severity == "error":
                should_block = True
            console.print(
                f"[{color}]✘[/{color}]  [bold {color}]{label}[/bold {color}]"
                f"  {severity_tag}"
            )
            for item in items:
                console.print(f"   {item}")
        console.print()

    total_issues: int = sum(issue_counts.values())
    console.print(Rule())
    if total_issues == 0:
        console.print("[bold green]✔ All clear — nothing flagged. Good to commit.[/bold green]")
    else:
        n_files = len(changed_files)
        file_word = "file" if n_files == 1 else "files"
        block_note = "  [red]commit blocked[/red]" if should_block else "  [dim]warnings only — commit allowed[/dim]"
        console.print(
            f"[bold]{total_issues} issue{'s' if total_issues != 1 else ''} found "
            f"across {n_files} {file_word}[/bold]{block_note}"
        )
        if should_block:
            console.print("[dim]Fix errors above, or `git commit --no-verify` to bypass.[/dim]")

    return should_block


def _strip_rich(text: str) -> str:
    """Remove rich markup tags, leaving plain text suitable for markdown."""
    return re.sub(r"\[/?[^\]]*\]", "", text)


def _build_report(
    results: dict,
    changed_files: list[str],
    branch: str,
    base_branch: str,
    config: SentinelConfig,
) -> str:
    sections = [
        ("readability",  "Readability"),
        ("dead_code",    "Dead Code"),
        ("blast_radius", "Blast Radius"),
    ]

    lines: list[str] = []

    # Header
    lines += [
        "# Sentinel Report",
        "",
        f"**Branch:** {branch}  ",
        f"**Base:** {base_branch}  ",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Files changed:** {', '.join(changed_files) if changed_files else '—'}",
        "",
    ]

    # Summary table
    lines += [
        "## Summary",
        "",
        "| Agent | Issues | Severity |",
        "|-------|--------|----------|",
    ]
    for key, label in sections:
        items = results.get(key, [])
        severity = getattr(config.severity, key, "warning")
        lines.append(f"| {label} | {len(items)} | {severity} |")
    lines.append("")

    # Per-agent sections
    for key, label in sections:
        items = results.get(key, [])
        lines.append(f"## {label}")
        lines.append("")
        if not items:
            lines.append("_Nothing flagged._")
        else:
            for item in items:
                # Each rich item may be multi-line (blast radius); indent
                # continuation lines so the bullet reads cleanly.
                plain = _strip_rich(item)
                for i, part in enumerate(plain.strip().splitlines()):
                    lines.append(f"- {part}" if i == 0 else f"  {part.strip()}")
        lines.append("")

    lines += ["---", "*Generated by sentinel*", ""]
    return "\n".join(lines)
