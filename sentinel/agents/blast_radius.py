"""
Blast radius agent — uses the pre-built call graph to find
callers of every function that was edited in the diff.
No LLM needed for MVP — this is pure static analysis.
"""


def run_blast_radius_agent(edited_functions: list[str], call_graph: dict) -> list[str]:
    """
    For each edited function, look up its callers in the call graph.
    Returns human-readable warning strings.
    """
    if not edited_functions:
        return []

    results = []

    for func in edited_functions:
        callers = call_graph.get(func, [])
        if not callers:
            continue

        caller_strs = ", ".join(
            f"[bold]{c['caller']}()[/bold] [{c['file']}:{c['line']}]"
            for c in callers[:5]  # cap at 5 for readability
        )
        results.append(
            f"  [red]⚡[/red] You edited [bold]{func}()[/bold]\n"
            f"     Callers: {caller_strs}\n"
            f"     [dim]→ Verify these still behave correctly[/dim]"
        )

    return results
