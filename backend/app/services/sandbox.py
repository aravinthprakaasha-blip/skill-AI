"""Code execution: Judge0 (isolated sandbox) with a dev-only local subprocess fallback.

Security model for hidden tests: only test *inputs* are sent to the sandbox (via stdin, or as
literals for Java). Expected outputs never leave the server, and comparison happens here, so a
submission cannot read or forge the answers. Results are read from a per-run random marker line.
"""
import asyncio
import base64
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time

import httpx

from ..config import get_settings

settings = get_settings()

LANGUAGES = {
    "python": {"judge0_id": 71, "file": "main.py", "monaco": "python"},
    "javascript": {"judge0_id": 63, "file": "main.js", "monaco": "javascript"},
    "typescript": {"judge0_id": 74, "file": "main.ts", "monaco": "typescript"},
    "java": {"judge0_id": 62, "file": "Main.java", "monaco": "java"},
}
MAX_OUTPUT = 64_000

# ---------------- harness generation ----------------

_PY = '''

def __sf_run():
    import json as _j, sys as _s
    _calls = _j.loads(_s.stdin.read() or "[]")
    _out = []
    for _c in _calls:
        try:
            if "cls" in _c:
                _o = globals()[_c["cls"]](*_c.get("init", []))
                _out.append({"ok": True, "value": [getattr(_o, _m)(*_a) for _m, _a in _c["ops"]]})
            else:
                _out.append({"ok": True, "value": globals()[_c["fn"]](*_c["args"])})
        except BaseException as _e:
            _out.append({"ok": False, "error": type(_e).__name__ + ": " + str(_e)[:200]})
    _s.stdout.write("\\n__MARK__" + _j.dumps(_out, default=str) + "\\n")
__sf_run()
'''

_JS = '''
;(function () {
  const __calls = JSON.parse(require("fs").readFileSync(0, "utf8") || "[]");
  const __out = [];
  const __n = (v) => (v === undefined ? null : v);
  for (const c of __calls) {
    try {
      if (c.cls) {
        const K = eval(c.cls);
        const o = new K(...(c.init || []));
        __out.push({ ok: true, value: c.ops.map((op) => __n(o[op[0]](...op[1]))) });
      } else {
        __out.push({ ok: true, value: __n(eval(c.fn)(...c.args)) });
      }
    } catch (e) {
      __out.push({ ok: false, error: String((e && e.message) || e).slice(0, 200) });
    }
  }
  process.stdout.write("\\n__MARK__" + JSON.stringify(__out) + "\\n");
})();
'''

_TS_DECL = "declare const require: any;\ndeclare const process: any;\n"

_JAVA_SER = '''
  static String ser(Object o) {
    if (o == null) return "null";
    if (o instanceof String) {
      StringBuilder b = new StringBuilder("\\"");
      for (char ch : ((String) o).toCharArray()) {
        if (ch == '"' || ch == '\\\\') b.append('\\\\').append(ch);
        else if (ch == '\\n') b.append("\\\\n");
        else if (ch < 32) b.append(' ');
        else b.append(ch);
      }
      return b.append("\\"").toString();
    }
    if (o instanceof Character) return ser(String.valueOf(o));
    if (o instanceof Number || o instanceof Boolean) return String.valueOf(o);
    if (o instanceof int[]) { List<Object> l = new ArrayList<>(); for (int v : (int[]) o) l.add(v); return ser(l); }
    if (o instanceof long[]) { List<Object> l = new ArrayList<>(); for (long v : (long[]) o) l.add(v); return ser(l); }
    if (o instanceof double[]) { List<Object> l = new ArrayList<>(); for (double v : (double[]) o) l.add(v); return ser(l); }
    if (o instanceof boolean[]) { List<Object> l = new ArrayList<>(); for (boolean v : (boolean[]) o) l.add(v); return ser(l); }
    if (o instanceof Object[]) return ser(Arrays.asList((Object[]) o));
    if (o instanceof Collection) {
      StringBuilder b = new StringBuilder("[");
      boolean first = true;
      for (Object v : (Collection<?>) o) { if (!first) b.append(","); first = false; b.append(ser(v)); }
      return b.append("]").toString();
    }
    if (o instanceof Map) {
      StringBuilder b = new StringBuilder("{");
      boolean first = true;
      for (Map.Entry<?, ?> e : ((Map<?, ?>) o).entrySet()) {
        if (!first) b.append(","); first = false;
        b.append(ser(String.valueOf(e.getKey()))).append(":").append(ser(e.getValue()));
      }
      return b.append("}").toString();
    }
    return ser(String.valueOf(o));
  }
'''


class HarnessError(ValueError):
    pass


def _java_literal(value, typ: str) -> str:
    typ = typ.strip()
    if typ.endswith("[]"):
        inner = typ[:-2]
        return f"new {typ}{{" + ", ".join(_java_literal(v, inner) for v in value) + "}"
    if typ in ("int", "long", "double"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HarnessError(f"bad {typ} literal")
        return f"{value}L" if typ == "long" else (repr(float(value)) if typ == "double" else str(int(value)))
    if typ == "boolean":
        return "true" if value else "false"
    if typ == "String":
        return json.dumps(str(value))  # JSON string escaping is valid Java for these inputs
    raise HarnessError(f"unsupported Java type {typ}")


def _java_program(code: str, calls: list[dict], signature: dict, mark: str) -> str:
    imports = re.findall(r"^\s*import\s+[\w.*]+\s*;\s*$", code, flags=re.M)
    body = re.sub(r"^\s*import\s+[\w.*]+\s*;\s*$", "", code, flags=re.M)
    body = re.sub(r"\bpublic\s+(?=(final\s+)?class\s)", "", body)  # only Main may be public
    stmts = []
    for c in calls:
        if "fn" not in c or c["fn"] not in signature:
            raise HarnessError("Java is not supported for this test shape")
        types = signature[c["fn"]]
        args = ", ".join(_java_literal(v, t) for v, t in zip(c["args"], types))
        stmts.append(
            f'    try {{ r.add("{{\\"ok\\":true,\\"value\\":" + ser(Solution.{c["fn"]}({args})) + "}}"); }}'
            f' catch (Throwable t) {{ r.add("{{\\"ok\\":false,\\"error\\":" + ser(String.valueOf(t)) + "}}"); }}'
        )
    return (
        "import java.util.*;\n"
        + "\n".join(i.strip() for i in imports)
        + "\npublic class Main {\n"
        + _JAVA_SER
        + "  public static void main(String[] args) {\n    List<String> r = new ArrayList<>();\n"
        + "\n".join(stmts)
        + f'\n    System.out.println("\\n{mark}[" + String.join(",", r) + "]");\n  }}\n}}\n\n'
        + body
    )


def _rename(call: dict, names: dict) -> dict:
    if not names:
        return call
    c = dict(call)
    for key in ("fn", "cls"):
        if key in c:
            c[key] = names.get(c[key], c[key])
    if "ops" in c:
        c["ops"] = [[names.get(m, m), a] for m, a in c["ops"]]
    return c


def build_program(language: str, code: str, calls: list[dict], lang_cfg: dict, mark: str) -> tuple[str, str]:
    """Returns (source, stdin)."""
    calls = [_rename(c, lang_cfg.get("names", {})) for c in calls]
    stdin = json.dumps(calls)
    if language == "python":
        return code + _PY.replace("__MARK__", mark), stdin
    if language == "javascript":
        return code + "\n" + _JS.replace("__MARK__", mark), stdin
    if language == "typescript":
        return _TS_DECL + code + "\n" + _JS.replace("__MARK__", mark), stdin
    if language == "java":
        return _java_program(code, calls, lang_cfg.get("signature", {}), mark), ""
    raise HarnessError(f"Unsupported language {language}")


# ---------------- executors ----------------


def engine_name() -> str:
    engines = []
    if settings.judge0_url:
        engines.append("judge0")
    if settings.runner_url:
        engines.append("runner")
    if settings.allow_local_runner:
        engines.append("local-runner")
    return "+".join(engines) or "unavailable"


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _unb64(s: str | None) -> str:
    return base64.b64decode(s).decode(errors="replace") if s else ""


async def _judge0(language: str, source: str, stdin: str) -> dict:
    headers = {"Content-Type": "application/json"}
    rapidapi = "rapidapi.com" in settings.judge0_url
    if settings.judge0_api_key:
        if rapidapi:
            headers["X-RapidAPI-Key"] = settings.judge0_api_key
            headers["X-RapidAPI-Host"] = httpx.URL(settings.judge0_url).host
        else:
            headers["X-Auth-Token"] = settings.judge0_api_key
    body = {
        "source_code": _b64(source),
        "language_id": LANGUAGES[language]["judge0_id"],
        "stdin": _b64(stdin),
        "cpu_time_limit": settings.exec_time_limit_s,
        "wall_time_limit": settings.exec_time_limit_s * 2,
        "memory_limit": settings.exec_memory_limit_kb,
        "enable_network": False,
    }
    base = settings.judge0_url.rstrip("/")
    async with httpx.AsyncClient(timeout=60, headers=headers) as client:
        if rapidapi:
            # Hosted quota counts every request: one blocking call instead of submit + polling.
            r = await client.post(f"{base}/submissions?base64_encoded=true&wait=true", json=body)
            r.raise_for_status()
            data = r.json()
            sid = data["status"]["id"]
            return _judge0_result(data, sid)
        r = await client.post(f"{base}/submissions?base64_encoded=true&wait=false", json=body)
        r.raise_for_status()
        token = r.json()["token"]
        deadline = time.monotonic() + settings.exec_time_limit_s * 2 + 30
        while True:
            r = await client.get(f"{base}/submissions/{token}?base64_encoded=true")
            r.raise_for_status()
            data = r.json()
            sid = data["status"]["id"]
            if sid > 2:
                break
            if time.monotonic() > deadline:
                return {"status": "timeout", "stdout": "", "stderr": "Sandbox queue timeout", "engine": "judge0"}
            await asyncio.sleep(0.4)
    return _judge0_result(data, sid)


def _judge0_result(data: dict, sid: int) -> dict:
    status = {3: "ok", 5: "timeout", 6: "compile_error"}.get(sid, "runtime_error" if sid >= 7 else "ok")
    return {
        "status": status,
        "stdout": _unb64(data.get("stdout"))[:MAX_OUTPUT],
        "stderr": (_unb64(data.get("stderr")) or _unb64(data.get("compile_output")) or data.get("message") or "")[
            :MAX_OUTPUT
        ],
        "time_ms": int(float(data.get("time") or 0) * 1000),
        "memory_kb": data.get("memory"),
        "engine": "judge0",
    }


def _local_sync(language: str, source: str, stdin: str) -> dict:
    """DEV ONLY: time-limited subprocess with a scrubbed environment. Not a security sandbox."""
    cfg = LANGUAGES[language]
    with tempfile.TemporaryDirectory(prefix="sf_run_") as tmp:
        path = os.path.join(tmp, cfg["file"])
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)
        cmd = {
            "python": [sys.executable, "-I", path],
            "javascript": ["node", path],
            "typescript": ["node", "--experimental-strip-types", "--no-warnings", path],
            "java": ["java", "-Xmx256m", path],
        }[language]
        env = {k: v for k, v in os.environ.items() if k.upper() in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "JAVA_HOME")}
        limit = settings.exec_time_limit_s + (15 if language == "java" else 2)
        start = time.monotonic()
        try:
            p = subprocess.run(
                cmd, input=stdin.encode(), capture_output=True, timeout=limit, cwd=tmp, env=env
            )
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "stdout": "", "stderr": f"Time limit exceeded ({limit:.0f}s)", "engine": "local-runner"}
        except FileNotFoundError:
            return {"status": "unavailable", "stdout": "", "stderr": f"Runtime for {language} is not installed", "engine": "local-runner"}
        elapsed = int((time.monotonic() - start) * 1000)
        return {
            "status": "ok" if p.returncode == 0 else "runtime_error",
            "stdout": p.stdout.decode(errors="replace")[:MAX_OUTPUT],
            "stderr": p.stderr.decode(errors="replace")[:MAX_OUTPUT].replace(tmp, ""),
            "time_ms": elapsed,
            "memory_kb": None,
            "engine": "local-runner",
        }


def _judge0_error(exc: Exception) -> str:
    """Actionable, secret-free description of a Judge0 failure."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        hint = {401: "invalid API key or token", 403: "not subscribed or key not allowed", 429: "quota exceeded"}.get(code, "")
        return f"HTTP {code}{': ' + hint if hint else ''}"
    return type(exc).__name__


async def _runner(language: str, source: str, stdin: str) -> dict:
    """Separate secret-free runner service (see runner/). Generous timeout covers free-tier cold starts."""
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{settings.runner_url.rstrip('/')}/run",
                              headers={"X-Runner-Token": settings.runner_token},
                              json={"language": language, "source": source, "stdin": stdin})
        r.raise_for_status()
        data = r.json()
    data["stdout"] = (data.get("stdout") or "")[:MAX_OUTPUT]
    data["stderr"] = (data.get("stderr") or "")[:MAX_OUTPUT]
    return data


async def execute(language: str, source: str, stdin: str) -> dict:
    """Try each configured engine in order; move on only when an engine itself fails
    (unreachable, quota, auth), never because of the learner's code."""
    failures = []
    if settings.judge0_url:
        try:
            return await _judge0(language, source, stdin)
        except Exception as exc:
            failures.append(f"Judge0: {_judge0_error(exc)}")
    if settings.runner_url:
        try:
            return await _runner(language, source, stdin)
        except Exception as exc:
            failures.append(f"runner: {_judge0_error(exc)}")
    if settings.allow_local_runner:
        return await asyncio.to_thread(_local_sync, language, source, stdin)
    detail = "; ".join(failures) or "no execution engine configured"
    return {"status": "unavailable", "stdout": "", "stderr": f"Code execution unavailable ({detail})", "engine": engine_name()}


# ---------------- test running ----------------


def _equal(actual, expected, unordered: bool = False) -> bool:
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return abs(float(actual) - float(expected)) <= 1e-6 * max(1.0, abs(float(expected)))
        except (TypeError, ValueError):
            return False
    if isinstance(expected, list) and isinstance(actual, list):
        if len(actual) != len(expected):
            return False
        if unordered:
            key = lambda v: json.dumps(v, sort_keys=True)  # noqa: E731
            actual, expected = sorted(actual, key=key), sorted(expected, key=key)
        return all(_equal(a, e) for a, e in zip(actual, expected))
    if isinstance(expected, dict) and isinstance(actual, dict):
        return expected.keys() == actual.keys() and all(_equal(actual[k], expected[k]) for k in expected)
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected
    return actual == expected


def _report(tests: list[dict], payload, res: dict, reveal: bool, show_output: bool, stdout: str) -> dict:
    results = []
    for i, t in enumerate(tests):
        name = t.get("name", f"Test {i + 1}") if reveal else f"Hidden test {i + 1}"
        r = payload[i] if isinstance(payload, list) and i < len(payload) else None
        if r is None:
            item = {"name": name, "passed": False, "error": res["status"] if res["status"] != "ok" else "no result"}
        elif not r.get("ok"):
            item = {"name": name, "passed": False, "error": r.get("error", "error") if reveal else "runtime error"}
        else:
            ok = _equal(r.get("value"), t["expected"], t.get("unordered", False))
            item = {"name": name, "passed": ok}
            if reveal and not ok:
                item["actual"], item["expected"] = r.get("value"), t["expected"]
        if reveal:
            item["input"] = t["call"]
        results.append(item)
    passed = bool(results) and all(r["passed"] for r in results)
    always = res["status"] in ("compile_error", "timeout", "unavailable")
    return {
        "status": res["status"],
        "passed": passed,
        "passed_count": sum(r["passed"] for r in results),
        "total": len(results),
        "results": results,
        "stdout": stdout if show_output else "",
        "stderr": res.get("stderr", "") if show_output or always else "",
        "time_ms": res.get("time_ms"),
        "memory_kb": res.get("memory_kb"),
        "engine": res.get("engine"),
        "limits": {"time_s": settings.exec_time_limit_s, "memory_kb": settings.exec_memory_limit_kb},
    }


async def run_suites(language: str, code: str, lang_cfg: dict, suites: list[tuple[list[dict], bool]]) -> list[dict]:
    """Run several test suites in ONE sandbox execution (saves hosted Judge0 quota).

    Each suite is (tests, reveal). Program output is only shown when every suite is revealed:
    a combined run's stdout/stderr could otherwise echo hidden test inputs.
    """
    mark = f"__SF_{secrets.token_hex(12)}__"
    all_tests = [t for tests, _ in suites for t in tests]
    try:
        source, stdin = build_program(language, code, [t["call"] for t in all_tests], lang_cfg, mark)
    except HarnessError as exc:
        err = {"status": "error", "passed": False, "passed_count": 0, "results": [], "stdout": "", "stderr": str(exc), "engine": engine_name()}
        return [{**err, "total": len(tests)} for tests, _ in suites]
    res = await execute(language, source, stdin)
    stdout = res.get("stdout", "")
    payload = None
    idx = stdout.rfind(mark)
    if idx >= 0:
        try:
            payload = json.loads(stdout[idx + len(mark) :].strip().splitlines()[0])
        except (ValueError, IndexError):
            payload = None
        stdout = stdout[:idx].rstrip("\n")
    show_output = all(reveal for _, reveal in suites)
    reports, offset = [], 0
    for tests, reveal in suites:
        part = payload[offset : offset + len(tests)] if isinstance(payload, list) else None
        reports.append(_report(tests, part, res, reveal, show_output, stdout))
        offset += len(tests)
    return reports


async def run_tests(language: str, code: str, tests: list[dict], lang_cfg: dict, reveal: bool) -> dict:
    """Run one suite. With reveal=False (hidden tests) only pass/fail is reported."""
    return (await run_suites(language, code, lang_cfg, [(tests, reveal)]))[0]
