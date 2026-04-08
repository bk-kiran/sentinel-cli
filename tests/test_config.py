"""
Tests for sentinel.core.config — SentinelConfig loading and defaults.
"""
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sentinel.core.config import (
    SentinelConfig,
    AgentsConfig,
    SeverityConfig,
    IgnoreConfig,
    load_config,
)


# ---------------------------------------------------------------------------
# Default config (no .sentinel.yml present)
# ---------------------------------------------------------------------------

def test_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path)
    assert isinstance(cfg, SentinelConfig)
    # agents all on
    assert cfg.agents.readability is True
    assert cfg.agents.dead_code is True
    assert cfg.agents.blast_radius is True
    # severity defaults
    assert cfg.severity.readability == "warning"
    assert cfg.severity.dead_code == "error"
    assert cfg.severity.blast_radius == "warning"
    # ignore lists empty
    assert cfg.ignore.paths == []
    assert cfg.ignore.functions == []


# ---------------------------------------------------------------------------
# Partial config merges with defaults
# ---------------------------------------------------------------------------

def test_partial_config_agents_only(tmp_path):
    (tmp_path / ".sentinel.yml").write_text(textwrap.dedent("""\
        agents:
          readability: false
    """))
    cfg = load_config(tmp_path)
    assert cfg.agents.readability is False
    # unspecified agents keep defaults
    assert cfg.agents.dead_code is True
    assert cfg.agents.blast_radius is True
    # severity untouched
    assert cfg.severity.dead_code == "error"


def test_partial_config_severity_only(tmp_path):
    (tmp_path / ".sentinel.yml").write_text(textwrap.dedent("""\
        severity:
          blast_radius: error
    """))
    cfg = load_config(tmp_path)
    assert cfg.severity.blast_radius == "error"
    # other severities keep defaults
    assert cfg.severity.readability == "warning"
    assert cfg.severity.dead_code == "error"


def test_partial_config_ignore_only(tmp_path):
    (tmp_path / ".sentinel.yml").write_text(textwrap.dedent("""\
        ignore:
          paths:
            - migrations/
          functions:
            - setup
    """))
    cfg = load_config(tmp_path)
    assert "migrations/" in cfg.ignore.paths
    assert "setup" in cfg.ignore.functions
    # agents still all on
    assert cfg.agents.readability is True


def test_empty_yml_uses_defaults(tmp_path):
    (tmp_path / ".sentinel.yml").write_text("")
    cfg = load_config(tmp_path)
    assert cfg.agents.readability is True
    assert cfg.severity.dead_code == "error"


def test_full_config_all_keys(tmp_path):
    (tmp_path / ".sentinel.yml").write_text(textwrap.dedent("""\
        agents:
          readability: false
          dead_code: false
          blast_radius: true
        severity:
          readability: error
          dead_code: warning
          blast_radius: error
        ignore:
          paths:
            - tests/
            - migrations/
          functions:
            - setup
            - teardown
    """))
    cfg = load_config(tmp_path)
    assert cfg.agents.readability is False
    assert cfg.agents.dead_code is False
    assert cfg.agents.blast_radius is True
    assert cfg.severity.readability == "error"
    assert cfg.severity.dead_code == "warning"
    assert cfg.severity.blast_radius == "error"
    assert cfg.ignore.paths == ["tests/", "migrations/"]
    assert cfg.ignore.functions == ["setup", "teardown"]


# ---------------------------------------------------------------------------
# CLI integration: disabled agent → skipped in output
# ---------------------------------------------------------------------------

def _make_results(readability=None, dead_code=None, blast_radius=None):
    return {
        "readability": readability or [],
        "dead_code": dead_code or [],
        "blast_radius": blast_radius or [],
    }


def test_disabled_agent_not_in_runner(tmp_path):
    """When an agent is disabled, run_agents receives it outside enabled_agents."""
    from sentinel.core.runner import run_agents

    called = []

    def fake_readability(diff):
        called.append("readability")
        return []

    def fake_dead_code(diff):
        called.append("dead_code")
        return []

    def fake_blast_radius(edited_functions, call_graph, max_depth=5):
        called.append("blast_radius")
        return []

    with (
        patch("sentinel.core.runner.run_readability_agent", fake_readability),
        patch("sentinel.core.runner.run_dead_code_agent", fake_dead_code),
        patch("sentinel.core.runner.run_blast_radius_agent", fake_blast_radius),
    ):
        run_agents(
            diff="+ def foo(): pass",
            call_graph={},
            edited_functions=["foo"],
            enabled_agents={"blast_radius"},  # readability + dead_code disabled
        )

    assert "readability" not in called
    assert "dead_code" not in called
    assert "blast_radius" in called


# ---------------------------------------------------------------------------
# CLI integration: severity → exit code
# ---------------------------------------------------------------------------

def _make_config(severity_dead_code="error", severity_readability="warning",
                 severity_blast_radius="warning"):
    cfg = SentinelConfig()
    cfg.severity.dead_code = severity_dead_code
    cfg.severity.readability = severity_readability
    cfg.severity.blast_radius = severity_blast_radius
    return cfg


def test_error_severity_returns_should_block_true():
    """_render_results must return True when an error-severity section has findings."""
    from sentinel.cli import _render_results
    from io import StringIO
    from rich.console import Console

    console_patch = Console(file=StringIO(), highlight=False)
    cfg = _make_config(severity_dead_code="error")
    results = _make_results(dead_code=["✗  foo.py:1  unused import os"])

    with patch("sentinel.cli.console", console_patch):
        should_block = _render_results(results, ["foo.py"], cfg)

    assert should_block is True


def test_warning_severity_returns_should_block_false():
    """_render_results must return False when all findings are warning-severity."""
    from sentinel.cli import _render_results
    from io import StringIO
    from rich.console import Console

    console_patch = Console(file=StringIO(), highlight=False)
    cfg = _make_config(
        severity_dead_code="warning",
        severity_readability="warning",
        severity_blast_radius="warning",
    )
    results = _make_results(
        readability=["⚠  foo.py:3  unclear name"],
        dead_code=["✗  foo.py:1  unused import"],
    )

    with patch("sentinel.cli.console", console_patch):
        should_block = _render_results(results, ["foo.py"], cfg)

    assert should_block is False


def test_mixed_severity_blocks_on_error_section():
    """A warning section with findings + an error section with findings → block."""
    from sentinel.cli import _render_results
    from io import StringIO
    from rich.console import Console

    console_patch = Console(file=StringIO(), highlight=False)
    cfg = _make_config(severity_readability="warning", severity_dead_code="error")
    results = _make_results(
        readability=["⚠  foo.py:5  magic number"],
        dead_code=["✗  foo.py:1  unused import"],
    )

    with patch("sentinel.cli.console", console_patch):
        should_block = _render_results(results, ["foo.py"], cfg)

    assert should_block is True


def test_error_severity_no_findings_does_not_block():
    """Error severity on a section with no findings must not block."""
    from sentinel.cli import _render_results
    from io import StringIO
    from rich.console import Console

    console_patch = Console(file=StringIO(), highlight=False)
    cfg = _make_config(severity_dead_code="error")
    results = _make_results()  # all empty

    with patch("sentinel.cli.console", console_patch):
        should_block = _render_results(results, ["foo.py"], cfg)

    assert should_block is False
