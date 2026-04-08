"""
Blast radius agent — uses the pre-built call graph to find ALL transitive
callers of every function that was edited in the diff.
No LLM needed — this is pure static analysis.
"""
from sentinel.core.parser import get_transitive_callers


def run_blast_radius_agent(
    edited_functions: list[str],
    call_graph: dict,
    max_depth: int = 5,
) -> list[str]:
    """
    For each edited function, walk the call graph transitively up to
    *max_depth* hops and return human-readable warning strings showing
    every affected caller with its depth.
    """
    if not edited_functions:
        return []

    results = []

    for func in edited_functions:
        callers = get_transitive_callers(func, call_graph, max_depth=max_depth)
        if not callers:
            continue

        files_hit = {c["file"] for c in callers}
        n_funcs = len(callers)
        n_files = len(files_hit)
        file_word = "file" if n_files == 1 else "files"

        lines = [f"[red]⚡[/red] You edited [bold]{func}()[/bold]"]
        for c in callers:
            lines.append(
                f"   [dim]depth {c['depth']}[/dim] → "
                f"[bold]{c['caller']}()[/bold] "
                f"[[dim]{c['file']}:{c['line']}[/dim]]"
            )
        lines.append(
            f"   [dim]→ {n_funcs} function{'s' if n_funcs != 1 else ''} "
            f"affected across {n_files} {file_word}[/dim]"
        )

        results.append("\n".join(lines))

    return results
