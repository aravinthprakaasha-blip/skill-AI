import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import auth, learner, missions, public
from .config import get_settings
from .services import llm, sandbox

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("skillforge")


async def _stall_loop():
    while True:
        await asyncio.sleep(6 * 3600)
        try:
            await public.run_stall_scan()
        except Exception:
            log.exception("stall scan failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .seed import seed_all

    if settings.jwt_secret == "dev-only-change-me" and settings.app_env == "production":
        raise RuntimeError("JWT_SECRET must be set in production")
    await seed_all(settings.seed_demo_data)
    tasks = [asyncio.create_task(_stall_loop())]
    if settings.redis_url:
        from .events import redis_listener

        tasks.append(asyncio.create_task(redis_listener()))
    log.info("SkillForge ready | llm=%s | exec=%s", llm.engine_label(), sandbox.engine_name())
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="SkillForge AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list,
                   allow_origin_regex=settings.cors_origin_regex or None, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


for r in (auth.router, learner.router, missions.router, public.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    """Liveness + a trivial DB query (also keeps free-tier databases from pausing when pinged)."""
    from sqlalchemy import text

    from .db import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "unreachable",
                 "llm": llm.engine_label(), "execution": sandbox.engine_name()},
    )
