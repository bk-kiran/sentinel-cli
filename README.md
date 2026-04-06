# sentinel

> AI code guardian for Python. Catches readability issues, dead code, and blast-radius risks before they hit `main`.

```bash
pip install -e . && export ANTHROPIC_API_KEY=sk-... && sentinel install
```

---

## Demo

Stage any Python file and run `sentinel check`:

```
────────────────────────── sentinel  scratch/demo.py ───────────────────────────

✔  Readability

✔  Dead Code

✘  Blast Radius
     ⚡ You edited helper()
     Callers: process() , main()
     → Verify these still behave correctly
     ⚡ You edited process()
     Callers: main()
     → Verify these still behave correctly

────────────────────────────────────────────────────────────────────────────────
2 issues found across 1 file  fix above, or `git commit --no-verify` to bypass
```

**What this is telling you:** `helper()` is called by both `process()` and `main()` — touch it carelessly and you break two code paths simultaneously. `process()` flows into `main()`, so a subtle signature change can silently corrupt downstream behavior. The blast radius agent surfaces this in milliseconds using a static call graph, no LLM required. When the API key is set, the readability and dead code agents add a second layer: Claude reviews the diff line-by-line for unclear names, magic numbers, unused imports, and unreachable branches — the kind of nits that survive code review and rot quietly.

---

## How it works

- **Readability agent** — sends your staged diff to Claude and flags unclear variable names, magic numbers, missing docstrings, and deeply nested logic.
- **Dead code agent** — asks Claude to identify unused imports, unreachable branches after `return`/`raise`, and variables that are assigned but never read within the visible diff.
- **Blast radius agent** — builds a one-hop call graph from your repo using tree-sitter (no LLM) and lists every function that calls into the code you just edited.

---

## Setup

```bash
# 1. Install
git clone https://github.com/yourname/sentinel
cd sentinel
pip install -e .

# 2. Add your Anthropic key (required for readability + dead code agents)
export ANTHROPIC_API_KEY=sk-...

# 3. Wire it up as a pre-commit hook
sentinel install
```

From here, `sentinel check --strict` runs automatically on every `git commit` and exits non-zero if issues are found. Use `git commit --no-verify` to bypass when you need to.

```bash
# Run manually at any time
sentinel check

# Check a specific file without staging it
sentinel check --file path/to/file.py

# Remove the hook
sentinel uninstall
```
