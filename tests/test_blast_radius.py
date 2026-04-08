"""
Tests for sentinel.agents.blast_radius — pure static analysis, no LLM calls.
"""
import pytest

from sentinel.agents.blast_radius import run_blast_radius_agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_caller(caller: str, file: str = "foo.py", line: int = 10) -> dict:
    return {"caller": caller, "file": file, "line": line}


# ---------------------------------------------------------------------------
# Empty / no-op cases
# ---------------------------------------------------------------------------

def test_no_edited_functions_returns_empty():
    assert run_blast_radius_agent([], {"foo": [make_caller("bar")]}) == []


def test_empty_call_graph_returns_empty():
    assert run_blast_radius_agent(["foo"], {}) == []


def test_edited_function_not_in_call_graph():
    """Function edited but nobody calls it — no warnings."""
    assert run_blast_radius_agent(["orphan"], {"other": [make_caller("x")]}) == []


def test_both_empty():
    assert run_blast_radius_agent([], {}) == []


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------

def test_returns_list_of_strings():
    cg = {"foo": [make_caller("bar")]}
    result = run_blast_radius_agent(["foo"], cg)
    assert isinstance(result, list)
    assert all(isinstance(r, str) for r in result)


def test_one_result_per_edited_function_with_callers():
    cg = {
        "foo": [make_caller("bar")],
        "baz": [make_caller("qux")],
    }
    result = run_blast_radius_agent(["foo", "baz"], cg)
    assert len(result) == 2


def test_no_result_for_function_without_callers():
    cg = {"foo": [make_caller("bar")], "lone": []}
    result = run_blast_radius_agent(["foo", "lone"], cg)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Content correctness
# ---------------------------------------------------------------------------

def test_edited_function_name_in_output():
    cg = {"myfunc": [make_caller("caller_a")]}
    result = run_blast_radius_agent(["myfunc"], cg)
    assert len(result) == 1
    assert "myfunc" in result[0]


def test_caller_name_in_output():
    cg = {"target": [make_caller("alpha")]}
    result = run_blast_radius_agent(["target"], cg)
    assert "alpha" in result[0]


def test_file_and_line_in_output():
    cg = {"fn": [make_caller("caller_x", file="src/utils.py", line=42)]}
    result = run_blast_radius_agent(["fn"], cg)
    assert "src/utils.py" in result[0]
    assert "42" in result[0]


def test_multiple_callers_all_appear():
    cg = {
        "shared": [
            make_caller("a", line=1),
            make_caller("b", line=2),
            make_caller("c", line=3),
        ]
    }
    result = run_blast_radius_agent(["shared"], cg)
    assert len(result) == 1
    assert "a" in result[0]
    assert "b" in result[0]
    assert "c" in result[0]


# ---------------------------------------------------------------------------
# Cap at 5 callers
# ---------------------------------------------------------------------------

def test_all_direct_callers_shown():
    """All direct callers appear — transitive agent has no breadth cap."""
    callers = [make_caller(f"caller_{i}", line=i) for i in range(8)]
    cg = {"big": callers}
    result = run_blast_radius_agent(["big"], cg)
    assert len(result) == 1
    for i in range(8):
        assert f"caller_{i}" in result[0]


def test_max_depth_limits_transitive_chain():
    """Callers beyond max_depth are excluded from output."""
    # chain: target ← d1 ← d2 ← d3
    cg = {
        "target": [make_caller("d1", line=1)],
        "d1":     [make_caller("d2", line=2)],
        "d2":     [make_caller("d3", line=3)],
    }
    result = run_blast_radius_agent(["target"], cg, max_depth=2)
    assert len(result) == 1
    assert "d1" in result[0]
    assert "d2" in result[0]
    assert "d3" not in result[0]  # depth 3 — beyond cap


# ---------------------------------------------------------------------------
# Multiple edited functions, mixed presence in graph
# ---------------------------------------------------------------------------

def test_only_functions_with_callers_produce_output():
    cg = {"present": [make_caller("x")]}
    result = run_blast_radius_agent(["present", "absent"], cg)
    assert len(result) == 1
    assert "present" in result[0]


def test_order_matches_edited_functions_order():
    cg = {
        "alpha": [make_caller("x")],
        "beta":  [make_caller("y")],
        "gamma": [make_caller("z")],
    }
    result = run_blast_radius_agent(["gamma", "alpha", "beta"], cg)
    assert len(result) == 3
    assert "gamma" in result[0]
    assert "alpha" in result[1]
    assert "beta"  in result[2]
