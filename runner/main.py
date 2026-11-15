"""SkillForge code runner: a tiny, secret-free execution service.

It exists so that learners' code never runs inside the main backend, which holds the database URL
and API keys. Deploy it as its own service (e.g. a free Render web service).

Isolation, in layers (no Docker-in-Docker or kernel sandbox is available on free hosting):
  * The service stores no secrets except RUNNER_TOKEN, which callers must send.
  * Each run happens in a fresh temp directory, as the unprivileged `nobody` user (when the
    service runs as root, as in the provided Dockerfile), so it cannot write the app files or
    read the server process's environment (/proc/<pid>/environ is owner-only).
  * Kernel resource limits: CPU seconds, address space (Python), processes, open files,
    file size, no core dumps; plus a wall-clock timeout that kills the whole process group.
  * One execution at a time, so a run cannot starve or observe another.
  * Output is truncated.
Outbound network access cannot be blocked on most free hosts; that is the main residual risk,
which is why the service holds nothing worth stealing.
"""
import asyncio
import hmac
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

TOKEN = os.environ.get("RUNNER_TOKEN", "").strip()
TIME_LIMIT_S = float(os.environ.get("RUNNER_TIME_LIMIT_S", "5"))
MEMORY_MB = int(os.environ.get("RUNNER_MEMORY_MB", "256"))
MAX_OUTPUT = 64_000
IS_POSIX = os.name == "posix"

LANGS = {
    "python": ("main.py", lambda f: [sys.executable, "-I", "-S", f]),
    "javascript": ("main.js", lambda f: ["node", f"--max-old-space-size={MEMORY_MB}", f]),
    "typescript": ("main.ts", lambda f: ["node", f"--max-old-space-size={MEMORY_MB}", "--experimental-strip-types", "--no-warnings", f]),
    "java": ("Main.java", lambda f: ["java", f"-Xmx{MEMORY_MB}m", "-XX:+UseSerialGC", "-Xss8m", f]),
}

app = FastAPI(title="SkillForge runner", docs_url=None, redoc_url=None, openapi_url=None)
_lock = asyncio.Lock()


class RunIn(BaseModel):
    language: str
    source: str = Field(max_length=200_000)
    stdin: str = Field("", max_length=1_000_000)


def _limits(language: str):
    """Runs in the child just before exec (POSIX only)."""

    def apply():
        import resource

        os.setsid()
        cpu = int(TIME_LIMIT_S) + 1
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        if language == "python":
            # JVM and V8 reserve large virtual ranges, so they are capped by -Xmx / heap flags instead.
            mem = MEMORY_MB * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        if os.geteuid() == 0:
            os.setgroups([])
            os.setgid(65534)
            os.setuid(65534)  # nobody
            resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))  # per-uid: stops fork bombs

    return apply


def _run_sync(language: str, source: str, stdin: str) -> dict:
    filename, cmd = LANGS[language]
    workdir = tempfile.mkdtemp(prefix="run_")
    try:
        path = os.path.join(workdir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)
        if IS_POSIX and os.geteuid() == 0:
            os.chown(workdir, 65534, 65534)
            os.chown(path, 65534, 65534)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": workdir, "LANG": "C.UTF-8"}
        if not IS_POSIX:
            env.update({k: os.environ[k] for k in ("SYSTEMROOT", "TEMP", "TMP") if k in os.environ})
        wall = TIME_LIMIT_S * 2 + (10 if language == "java" else 2)
        start = time.monotonic()
        proc = subprocess.Popen(cmd(path), cwd=workdir, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, preexec_fn=_limits(language) if IS_POSIX else None)
        try:
            out, err = proc.communicate(stdin.encode(), timeout=wall)
        except subprocess.TimeoutExpired:
            _kill(proc)
            proc.communicate()
            return {"status": "timeout", "stdout": "", "stderr": f"Time limit exceeded ({wall:.0f}s)", "engine": "runner"}
        elapsed = int((time.monotonic() - start) * 1000)
        rc = proc.returncode
        if IS_POSIX and rc in (-signal.SIGXCPU, -signal.SIGKILL):
            return {"status": "timeout", "stdout": "", "stderr": "CPU time limit exceeded", "engine": "runner"}
        stderr = err.decode(errors="replace")[:MAX_OUTPUT].replace(workdir, "")
        if language == "java" and rc != 0 and "error:" in stderr and "Exception" not in stderr:
            status = "compile_error"
        else:
            status = "ok" if rc == 0 else "runtime_error"
        return {"status": status, "stdout": out.decode(errors="replace")[:MAX_OUTPUT], "stderr": stderr,
                "time_ms": elapsed, "memory_kb": None, "engine": "runner"}
    except FileNotFoundError:
        return {"status": "unavailable", "stdout": "", "stderr": f"Runtime for {language} is not installed", "engine": "runner"}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _kill(proc: subprocess.Popen) -> None:
    try:
        if IS_POSIX:
            os.killpg(proc.pid, signal.SIGKILL)  # the child called setsid(), so this kills its whole tree
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError):
        pass


@app.get("/health")
def health():
    return {"status": "ok", "languages": [k for k, (_, c) in LANGS.items() if shutil.which(c("x")[0])],
            "sandboxed_user": IS_POSIX and os.geteuid() == 0, "token_configured": bool(TOKEN)}


@app.post("/run")
async def run(body: RunIn, x_runner_token: str = Header(default="")):
    if not TOKEN or not hmac.compare_digest(x_runner_token.strip(), TOKEN):
        raise HTTPException(401, "Invalid runner token")
    if body.language not in LANGS:
        raise HTTPException(422, "Unsupported language")
    async with _lock:  # one execution at a time
        return await asyncio.to_thread(_run_sync, body.language, body.source, body.stdin)
