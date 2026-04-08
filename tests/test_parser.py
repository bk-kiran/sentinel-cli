"""
Tests for sentinel.core.parser — build_call_graph and extract_edited_functions.
"""
import textwrap
from pathlib import Path

import pytest

from sentinel.core.parser import (
    TREE_SITTER_AVAILABLE,
    build_call_graph,
    extract_edited_functions,
    get_transitive_callers,
)


# ---------------------------------------------------------------------------
# Sanity
# ---------------------------------------------------------------------------

def test_tree_sitter_available():
    """tree-sitter-python must initialise correctly at import time."""
    assert TREE_SITTER_AVAILABLE is True


# ---------------------------------------------------------------------------
# build_call_graph — basic cases
# ---------------------------------------------------------------------------

def test_simple_caller(tmp_path):
    """foo() calls bar() → bar has one caller entry pointing at foo."""
    (tmp_path / "ex.py").write_text(textwrap.dedent("""\
        def foo():
            bar()

        def bar():
            pass
    """))
    cg = build_call_graph(tmp_path)

    assert "bar" in cg
    callers = cg["bar"]
    assert len(callers) == 1
    assert callers[0]["caller"] == "foo"


def test_caller_file_and_line(tmp_path):
    """Caller entry records the correct file path and 1-based line number."""
    src = textwrap.dedent("""\
        def foo():
            x = 1
            bar()
    """)
    f = tmp_path / "mymod.py"
    f.write_text(src)
    cg = build_call_graph(tmp_path)

    entry = cg["bar"][0]
    assert entry["caller"] == "foo"
    assert entry["file"] == str(f)
    assert entry["line"] == 3  # bar() is on line 3


def test_attribute_call(tmp_path):
    """obj.helper() is recorded under the attribute name 'helper'."""
    (tmp_path / "ex.py").write_text(textwrap.dedent("""\
        def caller():
            obj.helper()
            plain()
    """))
    cg = build_call_graph(tmp_path)

    assert "helper" in cg
    assert cg["helper"][0]["caller"] == "caller"
    assert "plain" in cg
    assert cg["plain"][0]["caller"] == "caller"


def test_multiple_callers(tmp_path):
    """Two functions both calling the same target → two caller entries."""
    (tmp_path / "ex.py").write_text(textwrap.dedent("""\
        def a():
            shared()

        def b():
            shared()
    """))
    cg = build_call_graph(tmp_path)

    assert "shared" in cg
    callers = {e["caller"] for e in cg["shared"]}
    assert callers == {"a", "b"}


def test_nested_function_caller(tmp_path):
    """Calls inside a nested def are attributed to the inner function."""
    (tmp_path / "ex.py").write_text(textwrap.dedent("""\
        def outer():
            def inner():
                target()
            inner()
    """))
    cg = build_call_graph(tmp_path)

    # target() is called from inner, not outer
    assert "target" in cg
    assert cg["target"][0]["caller"] == "inner"

    # inner() is called from outer
    assert "inner" in cg
    assert cg["inner"][0]["caller"] == "outer"


def test_function_with_no_calls(tmp_path):
    """A function that makes no calls contributes nothing to the graph."""
    (tmp_path / "ex.py").write_text(textwrap.dedent("""\
        def solo():
            x = 1 + 2
            return x
    """))
    cg = build_call_graph(tmp_path)
    assert cg == {}


def test_multiple_files(tmp_path):
    """Calls from two different files are both captured."""
    (tmp_path / "a.py").write_text("def a():\n    shared()\n")
    (tmp_path / "b.py").write_text("def b():\n    shared()\n")
    cg = build_call_graph(tmp_path)

    assert "shared" in cg
    callers = {e["caller"] for e in cg["shared"]}
    assert callers == {"a", "b"}


def test_non_python_files_ignored(tmp_path):
    """JavaScript / text files are not parsed."""
    (tmp_path / "ex.js").write_text("function foo() { bar(); }")
    (tmp_path / "notes.txt").write_text("def fake(): call()")
    cg = build_call_graph(tmp_path)
    assert cg == {}


def test_empty_python_file(tmp_path):
    """An empty .py file does not crash and produces no entries."""
    (tmp_path / "empty.py").write_text("")
    cg = build_call_graph(tmp_path)
    assert cg == {}


def test_git_directory_excluded(tmp_path):
    """Files inside a .git subtree are not parsed."""
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    (git_dir / "pre_commit.py").write_text("def hook():\n    run()\n")
    cg = build_call_graph(tmp_path)
    assert cg == {}


def test_returns_plain_dict(tmp_path):
    """build_call_graph must return a plain dict, not a defaultdict."""
    (tmp_path / "ex.py").write_text("def foo():\n    bar()\n")
    cg = build_call_graph(tmp_path)
    assert type(cg) is dict


# ---------------------------------------------------------------------------
# extract_edited_functions
# ---------------------------------------------------------------------------

def test_extract_finds_added_defs():
    diff = textwrap.dedent("""\
        --- a/foo.py
        +++ b/foo.py
        @@ -1,2 +1,4 @@
        +def new_func(x):
        +    pass
         def existing():
        -    old()
        +    new()
        +def another(y, z):
        +    pass
    """)
    result = extract_edited_functions(diff)
    assert "new_func" in result
    assert "another" in result


def test_extract_ignores_removed_lines():
    diff = textwrap.dedent("""\
        --- a/foo.py
        +++ b/foo.py
        @@ -1,2 +1,1 @@
        -def removed():
        -    pass
    """)
    result = extract_edited_functions(diff)
    assert result == []


def test_extract_ignores_file_header_lines():
    """Lines starting with +++ (file header) must not be matched."""
    diff = "+++ b/foo.py\n+def real_func():\n+    pass\n"
    result = extract_edited_functions(diff)
    assert "real_func" in result
    # The +++ line itself must not produce a spurious match
    assert "b/foo" not in result


def test_extract_deduplicates():
    """Same function name appearing in multiple hunks → listed once."""
    diff = "+def dup():\n+    pass\n+def dup():\n+    pass\n"
    result = extract_edited_functions(diff)
    assert result.count("dup") == 1


def test_extract_empty_diff():
    assert extract_edited_functions("") == []


def test_extract_no_function_defs():
    diff = "+x = 1\n+y = 2\n+ result = x + y\n"
    assert extract_edited_functions(diff) == []


def test_extract_context_lines_ignored():
    """Lines without a leading + are context — def on them must be ignored."""
    diff = " def context_func():\n     pass\n"
    assert extract_edited_functions(diff) == []


# ---------------------------------------------------------------------------
# get_transitive_callers
# ---------------------------------------------------------------------------

def _cg(*edges: tuple[str, str], file: str = "f.py") -> dict:
    """
    Build a minimal call_graph from (callee, caller) pairs.
    call_graph[callee] = [{"caller": caller, "file": file, "line": 1}]
    """
    from collections import defaultdict
    cg: dict = defaultdict(list)
    for callee, caller in edges:
        cg[callee].append({"caller": caller, "file": file, "line": 1})
    return dict(cg)


def test_transitive_direct_caller_is_depth_1():
    """A function that directly calls the target appears at depth 1."""
    cg = _cg(("target", "direct"))
    result = get_transitive_callers("target", cg)
    assert len(result) == 1
    assert result[0]["caller"] == "direct"
    assert result[0]["depth"] == 1


def test_transitive_depth_2():
    """A caller of a caller appears at depth 2."""
    # chain: target ← direct ← indirect
    cg = _cg(("target", "direct"), ("direct", "indirect"))
    result = get_transitive_callers("target", cg)
    depths = {r["caller"]: r["depth"] for r in result}
    assert depths["direct"] == 1
    assert depths["indirect"] == 2


def test_transitive_multiple_at_same_depth():
    """Two independent direct callers both appear at depth 1."""
    cg = _cg(("target", "a"), ("target", "b"))
    result = get_transitive_callers("target", cg)
    callers = {r["caller"] for r in result}
    assert callers == {"a", "b"}
    assert all(r["depth"] == 1 for r in result)


def test_transitive_no_callers_returns_empty():
    """A function nobody calls → empty list."""
    cg = _cg(("other", "caller"))
    assert get_transitive_callers("lonely", cg) == []


def test_transitive_function_not_in_graph():
    """Function absent from call_graph entirely → empty list."""
    assert get_transitive_callers("ghost", {}) == []


def test_transitive_cycle_no_infinite_loop():
    """A → B → A cycle terminates cleanly; each function appears once."""
    # a calls target, b calls a, a calls b (cycle between a and b)
    cg = _cg(("target", "a"), ("a", "b"), ("b", "a"))
    result = get_transitive_callers("target", cg)
    caller_names = [r["caller"] for r in result]
    # must terminate and not contain duplicates
    assert len(caller_names) == len(set(caller_names))
    assert "a" in caller_names
    assert "b" in caller_names


def test_transitive_self_loop_safe():
    """A function that calls itself (self-loop) does not appear in results."""
    cg = _cg(("target", "caller"), ("caller", "caller"))
    result = get_transitive_callers("target", cg)
    caller_names = [r["caller"] for r in result]
    assert caller_names.count("caller") == 1  # appears once, not twice


def test_transitive_max_depth_cap():
    """Callers beyond max_depth are not returned."""
    # chain: target ← d1 ← d2 ← d3 ← d4 ← d5 ← d6
    edges = [("target", "d1"), ("d1", "d2"), ("d2", "d3"),
             ("d3", "d4"), ("d4", "d5"), ("d5", "d6")]
    cg = _cg(*edges)
    result = get_transitive_callers("target", cg, max_depth=5)
    depths = {r["caller"]: r["depth"] for r in result}
    assert "d5" in depths
    assert depths["d5"] == 5
    assert "d6" not in depths  # depth 6 — beyond cap


def test_transitive_max_depth_1_direct_only():
    """max_depth=1 returns only direct callers, nothing deeper."""
    cg = _cg(("target", "direct"), ("direct", "indirect"))
    result = get_transitive_callers("target", cg, max_depth=1)
    callers = {r["caller"] for r in result}
    assert "direct" in callers
    assert "indirect" not in callers


def test_transitive_result_includes_file_and_line():
    """Each result entry carries the file and line from the call graph."""
    cg: dict = {"target": [{"caller": "fn", "file": "src/mod.py", "line": 42}]}
    result = get_transitive_callers("target", cg)
    assert result[0]["file"] == "src/mod.py"
    assert result[0]["line"] == 42


def test_transitive_each_function_appears_once():
    """BFS guarantees each unique caller appears at most once (min depth)."""
    # diamond: target ← a, target ← b, a ← root, b ← root
    cg = _cg(("target", "a"), ("target", "b"), ("a", "root"), ("b", "root"))
    result = get_transitive_callers("target", cg)
    caller_names = [r["caller"] for r in result]
    assert caller_names.count("root") == 1
    assert caller_names.count("a") == 1
    assert caller_names.count("b") == 1
