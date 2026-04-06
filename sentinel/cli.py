import typer
from rich.console import Console
from rich.rule import Rule
from rich.text import Text
from pathlib import Path

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

    files_str = "  ".join(changed_files)
    console.print()
    console.print(Rule(f"[bold cyan]sentinel[/bold cyan]  [dim]{files_str}[/dim]"))
    console.print()

    call_graph = build_call_graph(Path("."))
    edited_functions = extract_edited_functions(diff)

    results = run_agents(diff=diff, call_graph=call_graph, edited_functions=edited_functions)

    _render_results(results, changed_files)

    has_issues = any(results[k] for k in results)
    if strict and has_issues:
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
    console.print("[green]checkmark[/green] sentinel installed as pre-commit hook.")


@app.command()
def uninstall():
    """Remove the sentinel pre-commit hook."""
    hook_path = Path(".git/hooks/pre-commit")
    if hook_path.exists():
        hook_path.unlink()
        console.print("[green]checkmark[/green] sentinel hook removed.")
    else:
        console.print("[yellow]No pre-commit hook found.[/yellow]")


def _render_results(results: dict, changed_files: list[str]):
    sections = [
        ("readability", "Readability", "yellow"),
        ("dead_code",   "Dead Code",   "magenta"),
        ("blast_radius","Blast Radius","red"),
    ]

    total_issues = 0

    for key, label, color in sections:
        items = results.get(key, [])
        if not items:
            console.print(f"[green]✔[/green]  [bold]{label}[/bold]")
        else:
            total_issues += len(items)
            console.print(f"[{color}]✘[/{color}]  [bold {color}]{label}[/bold {color}]")
            for item in items:
                console.print(f"   {item}")
        console.print()

    console.print(Rule())
    if total_issues == 0:
        console.print("[bold green]✔ All clear — nothing flagged. Good to commit.[/bold green]")
    else:
        n_files = len(changed_files)
        file_word = "file" if n_files == 1 else "files"
        console.print(
            f"[bold red]{total_issues} issue{'s' if total_issues != 1 else ''} found "
            f"across {n_files} {file_word}[/bold red]  "
            "[dim]fix above, or `git commit --no-verify` to bypass[/dim]"
        )
