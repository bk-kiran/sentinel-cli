import typer
from rich.console import Console
from rich.rule import Rule
from pathlib import Path

from sentinel.core.config import load_config, SentinelConfig
from sentinel.core.git import get_staged_diff, get_staged_files
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
    )

    should_block = _render_results(results, changed_files, config)

    if should_block or (strict and any(results[k] for k in results)):
        raise typer.Exit(1)


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
