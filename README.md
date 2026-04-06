# sentinel 🛡️

> An agentic pre-commit code guardian for Python projects.

Sentinel runs before every commit and dispatches three specialized AI agents across your staged diff:

- **Readability agent** — naming, complexity, magic numbers
- **Dead code agent** — unused imports, unreachable branches, stale TODOs  
- **Blast radius agent** — traces who calls your edited functions (one-hop call graph)

## Install

```bash
pip install sentinel-cli  # coming soon to PyPI
```

Or from source:

```bash
git clone https://github.com/yourname/sentinel
cd sentinel
pip install -e .
```

## Usage

```bash
# Run manually on staged changes
sentinel check

# Install as a git pre-commit hook (auto-runs on every commit)
sentinel install

# Remove the hook
sentinel uninstall

# Check a specific file (bypass git staging)
sentinel check --file path/to/file.py
```

## Setup

```bash
export ANTHROPIC_API_KEY=your_key_here
```

## Output example

```
🛡️  sentinel — analyzing staged changes...

📁  Changed: auth.py, payments.py

🔍 Readability
  ⚠  auth.py:42  Variable `x` is unclear — consider `user_token`
  ⚠  payments.py:18  Magic number 86400 — extract as SECONDS_IN_DAY

🧹 Dead Code  
  ✗  auth.py:12  Unused import: `hashlib`
  ✗  payments.py:67  Unreachable branch after return on line 65

💥 Blast Radius
  ⚡ You edited `process_payment()` in payments.py
     Callers found: checkout() [orders.py:34], retry_handler() [jobs.py:91]
     → Verify these still behave correctly

✅  No blocking issues. Commit when ready.
```