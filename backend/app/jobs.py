"""Workflow dispatch. Long-running runs go to an RQ worker (Redis) or an in-process asyncio task."""
import asyncio
import logging

from .config import get_settings
from .db import session_scope
from .models import WorkflowRun

log = logging.getLogger("skillforge.jobs")
settings = get_settings()
_tasks: set[asyncio.Task] = set()


def create_run(profile_id: str, event: str, payload: dict) -> str:
    with session_scope() as db:
        run = WorkflowRun(profile_id=profile_id, event=event, payload=payload)
        db.add(run)
        db.flush()
        return run.id


async def dispatch(profile_id: str, event: str, payload: dict, background: bool = False) -> dict:
    """Run an event through the agent graph. background=True returns immediately with a run id."""
    from .agents.graph import run_workflow

    run_id = create_run(profile_id, event, payload)
    if not background:
        return await run_workflow(run_id)
    if settings.redis_url:
        try:
            from redis import Redis
            from rq import Queue

            Queue("skillforge", connection=Redis.from_url(settings.redis_url)).enqueue(
                "app.agents.graph.run_workflow_job", run_id, job_timeout=180
            )
            return {"run_id": run_id, "status": "queued", "executor": "rq"}
        except Exception as exc:  # Redis down -> degrade to in-process execution
            log.warning("RQ enqueue failed (%s); running in-process", type(exc).__name__)
    task = asyncio.create_task(run_workflow(run_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"run_id": run_id, "status": "queued", "executor": "in-process"}
