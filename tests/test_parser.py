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
