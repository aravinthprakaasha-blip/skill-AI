"""Static audit of submissions: Python `ast` for Python, Tree-sitter for JS/TS/Java.

Produces a deterministic report: structural metrics, banned-construct violations,
hardcoded-output detection, required-pattern checks, and code facts used to ground the Micro-Viva.
"""
import ast
import json
import os
import re
import shutil
import subprocess

DEFAULT_BANNED = {
    "python": {
        "imports": {"os", "sys", "subprocess", "socket", "shutil", "pathlib", "importlib", "ctypes", "inspect",
                    "builtins", "pickle", "threading", "multiprocessing", "urllib", "requests", "http"},
        "calls": {"eval", "exec", "open", "__import__", "compile", "input", "globals", "locals", "exit", "quit",
                  "breakpoint", "getattr", "setattr", "vars"},
        "names": {"__file__", "__builtins__", "__loader__", "__spec__"},
    },
    "javascript": {
        "imports": {"fs", "child_process", "net", "http", "https", "os", "vm", "worker_threads", "cluster", "dgram",
                    "node:fs", "node:child_process", "node:net", "node:os", "node:vm", "node:http", "node:https"},
        "calls": {"eval", "Function", "require", "fetch", "setInterval"},
        "names": {"process", "globalThis", "__filename", "__dirname", "module"},
    },
    "java": {
        "imports": {"java.io", "java.nio", "java.net", "java.lang.reflect", "java.lang.invoke", "javax", "sun"},
        "calls": {"exit", "exec", "getRuntime", "forName", "loadLibrary"},
        "names": {"ProcessBuilder", "Runtime", "Thread", "ClassLoader", "Scanner"},
    },
}
DEFAULT_BANNED["typescript"] = DEFAULT_BANNED["javascript"]


def _violation(rule: str, message: str, line: int | None = None) -> dict:
    return {"rule": rule, "message": message, "line": line}


# ============================ Python ============================

_PY_DICT = {"dict", "defaultdict", "Counter", "OrderedDict"}
_PY_BRANCH = (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.IfExp, ast.AsyncFor)


def _py_complexity(node: ast.AST) -> int:
    c = 1
    for n in ast.walk(node):
        if isinstance(n, _PY_BRANCH):
            c += 1
        elif isinstance(n, ast.BoolOp):
            c += len(n.values) - 1
        elif isinstance(n, ast.comprehension):
            c += 1 + len(n.ifs)
    return c


def _py_depth(node: ast.AST, depth: int = 0) -> int:
    best = depth
    for child in ast.iter_child_nodes(node):
        nested = isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With))
        best = max(best, _py_depth(child, depth + (1 if nested else 0)))
    return best


def _py_hardcoded(fn: ast.FunctionDef) -> bool:
    """True when a function returns literals without computing anything from its inputs."""
    params = {a.arg for a in fn.args.args} - {"self"}
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value is not None]
    if not returns or not params:
        return False
    literal_returns = [r for r in returns if isinstance(r.value, ast.Constant) or (
        isinstance(r.value, (ast.List, ast.Tuple, ast.Dict)) and all(isinstance(x, ast.Constant) for x in ast.walk(r.value) if isinstance(x, ast.expr) and not isinstance(x, (ast.List, ast.Tuple, ast.Dict, ast.Load)))
    )]
    computes = any(isinstance(n, (ast.For, ast.While, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.BinOp, ast.AugAssign)) for n in ast.walk(fn))
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    literal_compares = 0
    for n in ast.walk(fn):
        if isinstance(n, ast.Compare) and isinstance(n.ops[0], ast.Eq):
            sides = [n.left, *n.comparators]
            if any(isinstance(s, (ast.Constant, ast.List, ast.Tuple)) for s in sides) and any(
                isinstance(s, ast.Name) and s.id in params for s in sides
            ):
                literal_compares += 1
    if literal_compares >= 3 and len(literal_returns) >= 3:
        return True
    return len(literal_returns) == len(returns) and len(returns) >= 2 and not computes and not calls


def analyze_python(code: str, banned: dict) -> dict:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"parse_ok": False, "violations": [_violation("syntax", f"Syntax error: {exc.msg}", exc.lineno)],
                "features": [], "functions": [], "classes": [], "imports": [], "metrics": {}}
    violations, imports, features = [], [], set()
    functions, classes = [], []
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""]
            for m in mods:
                imports.append(m)
                if m.split(".")[0] in banned["imports"]:
                    violations.append(_violation("banned_import", f"Import of `{m}` is not allowed", n.lineno))
                if m.split(".")[0] == "collections":
                    names = {a.name for a in n.names}
                    if names & _PY_DICT:
                        features.add("dict")
                    if "deque" in names:
                        features.add("deque")
        elif isinstance(n, ast.Call):
            name = n.func.id if isinstance(n.func, ast.Name) else (n.func.attr if isinstance(n.func, ast.Attribute) else "")
            if isinstance(n.func, ast.Name) and name in banned["calls"]:
                violations.append(_violation("banned_call", f"Call to `{name}()` is not allowed", n.lineno))
            if name in _PY_DICT:
                features.add("dict")
            if name in ("set", "frozenset"):
                features.add("set")
            if name == "deque":
                features.add("deque")
            if name in ("sorted", "sort"):
                features.add("builtin_sort")
            if name in ("heappush", "heappop", "heapify"):
                features.add("heap")
        elif isinstance(n, ast.Name) and n.id in banned["names"]:
            violations.append(_violation("banned_name", f"Use of `{n.id}` is not allowed", n.lineno))
        elif isinstance(n, ast.Attribute) and n.attr.startswith("__") and n.attr.endswith("__") and n.attr not in ("__init__", "__name__", "__class__", "__len__"):
            violations.append(_violation("banned_name", f"Dunder access `{n.attr}` is not allowed", n.lineno))
        elif isinstance(n, (ast.Dict, ast.DictComp)):
            features.add("dict")
        elif isinstance(n, (ast.Set, ast.SetComp)):
            features.add("set")
        elif isinstance(n, (ast.ListComp, ast.GeneratorExp, ast.DictComp, ast.SetComp)):
            features.add("comprehension")
        elif isinstance(n, (ast.For, ast.While)):
            features.add("loop")
        elif isinstance(n, ast.Try):
            features.add("try_except")
        elif isinstance(n, ast.Raise):
            features.add("raise")
        elif isinstance(n, ast.ClassDef):
            features.add("class")
            classes.append({"name": n.name, "line": n.lineno,
                            "methods": [m.name for m in n.body if isinstance(m, ast.FunctionDef)]})
        if isinstance(n, (ast.DictComp, ast.SetComp)):
            features.add("comprehension")
        if isinstance(n, ast.FunctionDef):
            calls = {c.func.id for c in ast.walk(n) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
            calls |= {c.func.attr for c in ast.walk(n) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
            recursive = n.name in calls
            loops = [x for x in ast.walk(n) if isinstance(x, (ast.For, ast.While))]
            if recursive:
                features.add("recursion")
            hard = _py_hardcoded(n)
            if hard:
                violations.append(_violation("hardcoded_output", f"`{n.name}` returns hardcoded values instead of computing a result", n.lineno))
            functions.append({
                "name": n.name, "line": n.lineno, "end_line": getattr(n, "end_lineno", n.lineno),
                "params": [a.arg for a in n.args.args], "complexity": _py_complexity(n),
                "recursive": recursive, "loops": len(loops),
                "loop_kinds": sorted({type(x).__name__.lower() for x in loops}),
                "calls": sorted(calls)[:12], "has_docstring": ast.get_docstring(n) is not None,
            })
    loc = len([ln for ln in code.splitlines() if ln.strip() and not ln.strip().startswith("#")])
    return {
        "parse_ok": True, "violations": violations, "features": sorted(features),
        "functions": sorted(functions, key=lambda f: f["line"]), "classes": classes, "imports": sorted(set(imports)),
        "metrics": {"loc": loc, "functions": len(functions), "classes": len(classes),
                    "max_complexity": max((f["complexity"] for f in functions), default=1),
                    "max_nesting": _py_depth(tree)},
    }


# ============================ Tree-sitter (JS / TS / Java) ============================

_PARSERS: dict = {}


def _parser(language: str):
    if language in _PARSERS:
        return _PARSERS[language]
    try:
        from tree_sitter import Language, Parser

        if language == "javascript":
            import tree_sitter_javascript as m

            lang = Language(m.language())
        elif language == "typescript":
            import tree_sitter_typescript as m

            lang = Language(m.language_typescript())
        else:
            import tree_sitter_java as m

            lang = Language(m.language())
        _PARSERS[language] = Parser(lang)
    except Exception:
        _PARSERS[language] = None
    return _PARSERS[language]


_TS_FUNCS = {"function_declaration", "method_definition", "arrow_function", "function_expression",
             "generator_function_declaration", "method_declaration", "constructor_declaration"}
_TS_LOOPS = {"for_statement", "for_in_statement", "while_statement", "do_statement", "enhanced_for_statement"}
_TS_BRANCH = _TS_LOOPS | {"if_statement", "switch_case", "switch_block_statement_group", "ternary_expression",
                          "catch_clause", "conditional_expression"}
_TS_NEST = _TS_LOOPS | {"if_statement", "try_statement", "switch_statement", "switch_expression"}
_MAPS = {"Map", "HashMap", "TreeMap", "LinkedHashMap", "Object", "WeakMap"}
_SETS = {"Set", "HashSet", "TreeSet", "LinkedHashSet", "WeakSet"}


def _txt(node) -> str:
    return node.text.decode(errors="replace") if node is not None else ""


def _walk(node):
    yield node
    for c in node.children:
        yield from _walk(c)


def _ts_fn_name(node) -> str:
    name = node.child_by_field_name("name")
    if name is not None:
        return _txt(name)
    parent = node.parent
    if parent is not None and parent.type in ("variable_declarator", "pair", "assignment_expression", "public_field_definition"):
        return _txt(parent.child_by_field_name("name") or parent.child_by_field_name("key") or parent.child_by_field_name("left"))
    return "<anonymous>"


def _ts_depth(node, depth=0) -> int:
    best = depth
    for c in node.children:
        best = max(best, _ts_depth(c, depth + (1 if c.type in _TS_NEST else 0)))
    return best


def _typescript_module() -> str | None:
    candidates = [os.environ.get("TYPESCRIPT_MODULE", ""),
                  os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "node_modules", "typescript"),
                  os.path.join(os.path.dirname(__file__), "..", "..", "node_modules", "typescript")]
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "package.json")):
            return os.path.abspath(c)
    return None


def analyze_typescript_compiler(code: str, language: str, banned: dict) -> dict | None:
    """Real AST via the TypeScript compiler API (Node). Used when Tree-sitter is unavailable."""
    mod, node = _typescript_module(), shutil.which("node")
    if not mod or not node:
        return None
    script = os.path.join(os.path.dirname(__file__), "ts_ast.js")
    lists = json.dumps({k: sorted(v) for k, v in banned.items()})
    try:
        p = subprocess.run([node, script, mod, lists, language], input=code.encode(), capture_output=True, timeout=20)
        return json.loads(p.stdout) if p.returncode == 0 else None
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None


def js_engine(language: str) -> str:
    if _parser(language):
        return "tree-sitter"
    if language in ("javascript", "typescript") and _typescript_module() and shutil.which("node"):
        return "typescript-compiler-ast"
    return "regex-fallback"


def analyze_tree_sitter(code: str, language: str, banned: dict) -> dict:
    parser = _parser(language)
    if parser is None:
        if language in ("javascript", "typescript"):
            rep = analyze_typescript_compiler(code, language, banned)
            if rep is not None:
                return rep
        return _analyze_regex(code, language, banned)
    root = parser.parse(code.encode()).root_node
    violations, imports, features, functions, classes = [], [], set(), [], []
    if root.has_error:
        bad = next((n for n in _walk(root) if n.type == "ERROR" or n.is_missing), root)
        violations.append(_violation("syntax", "Syntax error", bad.start_point[0] + 1))
    for n in _walk(root):
        t, line = n.type, n.start_point[0] + 1
        if t == "import_statement":
            src = _txt(n.child_by_field_name("source")).strip("'\"`")
            imports.append(src)
            if src in banned["imports"] or src.startswith("node:"):
                violations.append(_violation("banned_import", f"Import of `{src}` is not allowed", line))
        elif t == "import_declaration":
            src = _txt(n).replace("import", "").replace("static", "").strip(" ;\n")
            imports.append(src)
            if any(src == b or src.startswith(b + ".") for b in banned["imports"]):
                violations.append(_violation("banned_import", f"Import of `{src}` is not allowed", line))
        elif t in ("call_expression", "method_invocation"):
            fn = n.child_by_field_name("function") or n.child_by_field_name("name")
            name = _txt(fn).split(".")[-1]
            direct = fn is not None and fn.type == "identifier"
            if name in banned["calls"] and (direct or language == "java"):
                violations.append(_violation("banned_call", f"Call to `{name}()` is not allowed", line))
            if name == "sort":
                features.add("builtin_sort")
        elif t in ("new_expression", "object_creation_expression"):
            ctor = _txt(n.child_by_field_name("constructor") or n.child_by_field_name("type")).split("<")[0]
            if ctor in _MAPS:
                features.add("dict")
            if ctor in _SETS:
                features.add("set")
            if ctor in banned["calls"] or ctor in banned["names"]:
                violations.append(_violation("banned_call", f"`new {ctor}` is not allowed", line))
        elif t in ("identifier", "type_identifier") and _txt(n) in banned["names"]:
            violations.append(_violation("banned_name", f"Use of `{_txt(n)}` is not allowed", line))
        elif t == "object" and n.parent is not None and n.parent.type in ("variable_declarator", "assignment_expression"):
            features.add("dict")
        elif t in _TS_LOOPS:
            features.add("loop")
        elif t == "try_statement":
            features.add("try_except")
        elif t == "throw_statement":
            features.add("raise")
        elif t in ("class_declaration", "class"):
            features.add("class")
            body = n.child_by_field_name("body")
            classes.append({"name": _txt(n.child_by_field_name("name")), "line": line,
                            "methods": [_txt(m.child_by_field_name("name")) for m in (body.children if body else [])
                                        if m.type in ("method_definition", "method_declaration")]})
        if language == "java" and t in ("generic_type", "type_identifier"):
            base = _txt(n).split("<")[0]
            if base in _MAPS or base == "Map":
                features.add("dict")
            if base in _SETS:
                features.add("set")
        if t in _TS_FUNCS:
            name = _ts_fn_name(n)
            inner = list(_walk(n))
            calls = set()
            for c in inner:
                if c.type in ("call_expression", "method_invocation"):
                    calls.add(_txt(c.child_by_field_name("function") or c.child_by_field_name("name")).split(".")[-1])
            loops = [c for c in inner if c.type in _TS_LOOPS]
            recursive = name in calls and name != "<anonymous>"
            if recursive:
                features.add("recursion")
            complexity = 1 + sum(1 for c in inner if c.type in _TS_BRANCH) + sum(
                1 for c in inner if c.type == "binary_expression" and _txt(c.child_by_field_name("operator")) in ("&&", "||"))
            params = n.child_by_field_name("parameters")
            returns = [c for c in inner if c.type == "return_statement"]
            literal = {"number", "string", "true", "false", "null", "decimal_integer_literal", "string_literal", "array"}
            lit_returns = [r for r in returns if len(r.named_children) == 1 and r.named_children[0].type in literal]
            computes = loops or any(c.type in ("binary_expression", "augmented_assignment_expression", "update_expression") and
                                    _txt(c.child_by_field_name("operator")) not in ("===", "==", "!==", "!=") for c in inner)
            if name != "<anonymous>" and len(returns) >= 2 and len(lit_returns) == len(returns) and not computes and not calls:
                violations.append(_violation("hardcoded_output", f"`{name}` returns hardcoded values instead of computing a result", line))
            if name != "<anonymous>":
                functions.append({"name": name, "line": line, "end_line": n.end_point[0] + 1,
                                  "params": [_txt(p).split(":")[0].split(" ")[-1].strip() for p in (params.named_children if params else [])],
                                  "complexity": complexity, "recursive": recursive, "loops": len(loops),
                                  "loop_kinds": sorted({c.type.replace("_statement", "") for c in loops}),
                                  "calls": sorted(calls)[:12], "has_docstring": False})
    loc = len([ln for ln in code.splitlines() if ln.strip() and not ln.strip().startswith(("//", "*", "/*"))])
    return {
        "parse_ok": not root.has_error, "violations": violations, "features": sorted(features),
        "functions": sorted(functions, key=lambda f: f["line"]), "classes": classes, "imports": sorted(set(imports)),
        "metrics": {"loc": loc, "functions": len(functions), "classes": len(classes),
                    "max_complexity": max((f["complexity"] for f in functions), default=1),
                    "max_nesting": _ts_depth(root)},
    }


def _analyze_regex(code: str, language: str, banned: dict) -> dict:
    """Last-resort structural scan if Tree-sitter grammars are unavailable."""
    violations, features = [], set()
    for i, ln in enumerate(code.splitlines(), 1):
        for name in banned["calls"] | banned["names"]:
            if re.search(rf"\b{re.escape(name)}\b", ln):
                violations.append(_violation("banned_name", f"Use of `{name}` is not allowed", i))
        if re.search(r"\b(for|while)\b", ln):
            features.add("loop")
        if re.search(r"\bclass\b", ln):
            features.add("class")
    names = re.findall(r"(?:function\s+|static\s+[\w<>\[\]]+\s+)(\w+)\s*\(", code)
    return {"parse_ok": True, "violations": violations, "features": sorted(features),
            "functions": [{"name": n, "line": 0, "end_line": 0, "params": [], "complexity": 1, "recursive": False,
                           "loops": 0, "loop_kinds": [], "calls": [], "has_docstring": False} for n in names],
            "classes": [], "imports": [], "metrics": {"loc": len(code.splitlines()), "functions": len(names)}}


# ============================ rule evaluation ============================


def audit(code: str, language: str, rules: dict | None = None, names: dict | None = None) -> dict:
    """Run the analyzer and evaluate mission rules. Deterministic."""
    rules, names = rules or {}, names or {}
    base = DEFAULT_BANNED[language]
    banned = {
        "imports": base["imports"] | set(rules.get("banned_imports", [])),
        "calls": base["calls"] | set(rules.get("banned_calls", [])),
        "names": base["names"],
    }
    rep = analyze_python(code, banned) if language == "python" else analyze_tree_sitter(code, language, banned)
    engine = "python-ast" if language == "python" else js_engine(language)
    violations = list(rep["violations"])
    required = []
    defined = {f["name"] for f in rep["functions"]} | {m for c in rep["classes"] for m in c["methods"]}
    for fn in rules.get("required_functions", []):
        fn = names.get(fn, fn)
        required.append({"rule": f"defines `{fn}`", "satisfied": fn in defined})
    for cls in rules.get("required_classes", []):
        required.append({"rule": f"defines class `{cls}`", "satisfied": cls in {c['name'] for c in rep['classes']}})
    for feat in rules.get("require", []):
        required.append({"rule": f"uses {feat.replace('_', ' ')}", "satisfied": feat in rep["features"]})
    for feat in rules.get("forbid", []):
        if feat in rep["features"]:
            violations.append(_violation("forbidden_pattern", f"Solution must not use {feat.replace('_', ' ')}"))
    limit = rules.get("max_complexity")
    if limit and rep["metrics"].get("max_complexity", 0) > limit:
        violations.append(_violation("complexity", f"Cyclomatic complexity exceeds {limit}"))
    seen, unique = set(), []
    for v in violations:
        key = (v["rule"], v["message"])
        if key not in seen:
            seen.add(key)
            unique.append(v)
    passed = rep["parse_ok"] and not unique and all(r["satisfied"] for r in required)
    return {
        "engine": engine, "language": language, "passed": passed, "violations": unique, "required": required,
        "features": rep["features"], "functions": rep["functions"], "classes": rep["classes"],
        "imports": rep["imports"], "metrics": rep["metrics"],
    }
