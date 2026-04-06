"""
Dead code agent — reviews the diff for:
- Unused imports in changed files
- Unreachable code after return/raise/continue/break
- Stale TODO/FIXME/HACK comments
- Functions or variables defined but never referenced (in the diff context)
"""
import os
import anthropic

_SYSTEM = """\
You are a senior Python engineer doing a focused dead code review.
You will receive a unified git diff of Python code.

Flag ONLY real issues. Be concise. Each issue must be one line in this exact format:
  ✗  filename.py:LINE  Short description of the issue

Rules:
- Flag import statements in + lines that appear unused in the visible diff
- Flag code that is unreachable (after a return, raise, break, or continue)
- Flag TODO/FIXME/HACK comments older than the current change (in context lines)
- Flag variables assigned but never read within the visible scope
- DO NOT flag things you cannot verify from the diff alone
- If nothing is wrong, respond with exactly: NONE
"""


def run_dead_code_agent(diff: str) -> list[str]:
    """Call Claude to review diff for dead code. Returns list of issue strings."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return ["[dim]✗  ANTHROPIC_API_KEY not set — dead code agent skipped[/dim]"]
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": f"Review this diff:\n\n{diff}"}],
    )

    raw = message.content[0].text.strip()
    if raw == "NONE" or not raw:
        return []

    return [line.strip() for line in raw.splitlines() if line.strip()]
