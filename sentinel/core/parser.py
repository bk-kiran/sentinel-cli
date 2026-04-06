"""
Tree-sitter based parser for Python call graph construction.
Builds a one-hop call graph: for each function definition in the repo,
records which other functions it calls.
"""
from pathlib import Path
from collections import defaultdict

try:
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    PY_LANGUAGE = Language(tspython.language())
    _parser = Parser(PY_LANGUAGE)
    TREE_SITTER_AVAILABLE = True
except Exception:
    TREE_SITTER_AVAILABLE = False


def build_call_graph(repo_root: Path) -> dict[str, list[dict]]:
    """
    Scan all .py files under repo_root and build a one-hop call graph.

    Returns:
        call_graph: {
            "function_name": [
                {"caller": "other_func", "file": "path/to/file.py", "line": 42},
                ...
            ]
        }
    Each entry means: `caller` calls `function_name` at `line` in `file`.
    """
    if not TREE_SITTER_AVAILABLE:
        return {}

    # Map: function_name -> list of {caller, file, line}
    call_graph: dict[str, list[dict]] = defaultdict(list)

    _SKIP = {".git", ".venv", "venv", "__pycache__"}
    py_files = [
        p for p in repo_root.rglob("*.py")
        if not (_SKIP & set(p.parts) or "site-packages" in p.parts)
    ]

    for filepath in py_files:
        try:
            source = filepath.read_bytes()
            tree = _parser.parse(source)
            _extract_calls(tree.root_node, source, str(filepath), call_graph)
        except Exception:
            continue

    return dict(call_graph)


def _extract_calls(root, source: bytes, filepath: str, call_graph: dict):
    """
    Walk the AST. For each function_definition node, find all call expressions
    inside it and record: callee -> [{caller, file, line}].
    """
    current_function = None

    def walk(node):
        nonlocal current_function

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                prev = current_function
                current_function = source[name_node.start_byte:name_node.end_byte].decode()
                for child in node.children:
                    walk(child)
                current_function = prev
                return

        if node.type == "call" and current_function:
            func_node = node.child_by_field_name("function")
            if func_node:
                # Handle both plain calls `foo()` and attribute calls `obj.foo()`
                if func_node.type == "identifier":
                    callee = source[func_node.start_byte:func_node.end_byte].decode()
                elif func_node.type == "attribute":
                    attr = func_node.child_by_field_name("attribute")
                    callee = source[attr.start_byte:attr.end_byte].decode() if attr else None
                else:
                    callee = None

                if callee:
                    call_graph[callee].append({
                        "caller": current_function,
                        "file": filepath,
                        "line": func_node.start_point[0] + 1,
                    })

        for child in node.children:
            walk(child)

    walk(root)


def extract_edited_functions(diff: str) -> list[str]:
    """
    Parse a unified diff and extract the names of functions that were modified.
    Looks for `def function_name` in added/changed lines (+lines).
    """
    import re
    edited = []
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", line)
            if match:
                edited.append(match.group(1))
    return list(set(edited))
