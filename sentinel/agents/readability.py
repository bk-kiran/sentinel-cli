"""
Readability agent — reviews the diff for:
- Unclear variable/function names
- Magic numbers
- Deeply nested logic (complexity smell)
- Missing docstrings on public functions
"""
import os
import anthropic

_SYSTEM = """\
You are a senior Python engineer doing a focused readability review.
You will receive a unified git diff of Python code.

Flag ONLY real issues. Be concise. Each issue must be one line in this exact format:
  ⚠  filename.py:LINE  Short description of the issue

Rules:
- Flag unclear variable names (single letters, abbreviations like `x`, `tmp`, `val`)
- Flag magic numbers (bare integers/floats that should be named constants)
- Flag functions with no docstring that are longer than 5 lines
- Flag deeply nested logic (3+ levels of indentation)
- DO NOT flag style preferences, import ordering, or minor formatting
- If nothing is wrong, respond with exactly: NONE
"""


def run_readability_agent(diff: str) -> list[str]:
    """Call Claude to review diff for readability issues. Returns list of issue strings."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return ["[dim]⚠  ANTHROPIC_API_KEY not set — readability agent skipped[/dim]"]
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
