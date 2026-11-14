"""AI code review (advisory only - it never gates a tier). Gemini with a metric-based fallback."""
from . import llm

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "readability": {"type": "INTEGER"},
        "complexity": {"type": "INTEGER"},
        "modularity": {"type": "INTEGER"},
        "practices": {"type": "INTEGER"},
        "summary": {"type": "STRING"},
        "strengths": {"type": "ARRAY", "items": {"type": "STRING"}},
        "improvements": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["readability", "complexity", "modularity", "practices", "summary", "strengths", "improvements"],
}


def _clamp(v) -> int:
    try:
        return max(1, min(5, int(v)))
    except (TypeError, ValueError):
        return 3


def heuristic_review(code: str, ast_report: dict) -> dict:
    m = ast_report.get("metrics", {})
    fns = ast_report.get("functions", [])
    lines = [ln for ln in code.splitlines() if ln.strip()]
    long_lines = sum(1 for ln in lines if len(ln) > 100)
    short_names = sum(1 for f in fns for p in f["params"] if len(p) == 1)
    comments = sum(1 for ln in lines if ln.strip().startswith(("#", "//", "/*", "*", '"""')))
    cx, nest = m.get("max_complexity", 1), m.get("max_nesting", 0)
    longest = max((f["end_line"] - f["line"] + 1 for f in fns), default=0)
    readability = 5 - (1 if long_lines else 0) - (1 if short_names > 2 else 0) - (1 if nest > 3 else 0)
    complexity = 5 if cx <= 5 else 4 if cx <= 8 else 3 if cx <= 12 else 2
    modularity = 5 - (1 if longest > 30 else 0) - (1 if longest > 60 else 0) - (1 if not fns else 0)
    practices = 5 - min(3, len(ast_report.get("violations", []))) - (0 if comments or any(f["has_docstring"] for f in fns) else 1)
    strengths, improvements = [], []
    if cx <= 5:
        strengths.append(f"Low cyclomatic complexity (max {cx}) keeps the logic easy to follow.")
    else:
        improvements.append(f"Max cyclomatic complexity is {cx}; consider extracting a helper or flattening branches.")
    if longest and longest <= 30:
        strengths.append("Functions are short and focused.")
    elif longest > 30:
        improvements.append(f"Longest function spans {longest} lines; split it into smaller units.")
    if nest > 3:
        improvements.append(f"Nesting depth reaches {nest}; early returns would reduce it.")
    if long_lines:
        improvements.append(f"{long_lines} line(s) exceed 100 characters.")
    if short_names > 2:
        improvements.append("Several single-letter parameter names; descriptive names aid readability.")
    if not comments and not any(f["has_docstring"] for f in fns):
        improvements.append("No comments or docstrings explain intent.")
    for v in ast_report.get("violations", []):
        improvements.append(v["message"])
    return {
        "engine": "deterministic-fallback",
        "readability": _clamp(readability),
        "complexity": _clamp(complexity),
        "modularity": _clamp(modularity),
        "practices": _clamp(practices),
        "summary": f"Metric-based review: {m.get('loc', len(lines))} LOC, {len(fns)} function(s), max complexity {cx}, max nesting {nest}.",
        "strengths": strengths or ["Code parses cleanly and passes the structural audit."],
        "improvements": improvements,
    }


async def ai_review(code: str, language: str, mission_title: str, ast_report: dict) -> dict:
    prompt = (
        f"Review this {language} submission for the mission '{mission_title}'. Score each dimension 1-5 "
        "(5 best; for complexity, 5 = appropriately simple). Be specific and reference identifiers from the code. "
        "Do not rewrite the solution.\n\n"
        f"Static metrics: {ast_report.get('metrics')}\n\n```{language}\n{code[:6000]}\n```"
    )
    out = await llm.generate_json(prompt, SCHEMA, system="You are a senior engineer performing a concise code review.")
    if not out:
        return heuristic_review(code, ast_report)
    return {
        "engine": llm.engine_label(),
        **{k: _clamp(out.get(k)) for k in ("readability", "complexity", "modularity", "practices")},
        "summary": str(out.get("summary", ""))[:600],
        "strengths": [str(s)[:300] for s in out.get("strengths", [])][:5],
        "improvements": [str(s)[:300] for s in out.get("improvements", [])][:6],
    }
