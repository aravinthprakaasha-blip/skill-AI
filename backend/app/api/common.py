import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import AgentExecution, LearnerProfile, User, WorkflowRun


def user_out(db: Session, user: User) -> dict:
    prof = db.query(LearnerProfile).filter_by(user_id=user.id).first()
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "profile_id": prof.id if prof else None,
        "public_id": prof.public_id if prof else None,
        "onboarded": bool(prof and prof.onboarded),
    }


def run_out(db: Session, run: WorkflowRun) -> dict:
    steps = db.query(AgentExecution).filter_by(run_id=run.id).order_by(AgentExecution.seq).all()
    return {
        "id": run.id,
        "event": run.event,
        "status": run.status,
        "payload": run.payload,
        "event_chain": (run.result or {}).get("event_chain", []),
        "error": (run.result or {}).get("error"),
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "steps": [
            {"seq": s.seq, "agent": s.agent, "task": s.task, "status": s.status, "duration_ms": s.duration_ms,
             "output": s.output, "created_at": s.created_at.isoformat()}
            for s in steps
        ],
    }


def run_summary(run: dict) -> dict:
    """Compact synchronous-run result for API responses: trace steps with each agent's output."""
    outputs = run.get("outputs", {})
    return {
        "id": run["run_id"],
        "status": run["status"],
        "event_chain": run.get("event_chain", []),
        "error": run.get("error"),
        "steps": [{**t, "output": outputs.get(t["agent"], {})} for t in run.get("trace", [])],
    }


class RateLimiter:
    """Small in-process limiter for expensive endpoints (code execution, LLM calls)."""

    def __init__(self, per_seconds: float):
        self.per = per_seconds
        self.last: dict[str, float] = {}

    def check(self, key: str) -> None:
        now = time.monotonic()
        if now - self.last.get(key, 0) < self.per:
            raise HTTPException(429, "Too many requests - please wait a moment")
        self.last[key] = now
