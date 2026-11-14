"""Public recruiter verification ledger, admin dashboard and the realtime WebSocket."""
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..events import manager
from ..jobs import dispatch
from ..models import (
    AgentExecution,
    CareerRole,
    LearnerProfile,
    LedgerEntry,
    Mission,
    Resource,
    Skill,
    Submission,
    User,
    WorkflowRun,
    utcnow,
)
from ..security import require_role, user_from_token
from ..services import career, llm, sandbox, skill_dna
from .common import run_out

router = APIRouter(tags=["public"])


@router.get("/api/verify/{public_id}")
def verify(public_id: str, db: Session = Depends(get_db)):
    """Recruiter-safe view. Exposes only ledger entries (which never contain code, hidden tests,
    email, education or answers), public project links and computed match score."""
    p = db.query(LearnerProfile).filter_by(public_id=public_id).first()
    if not p or not p.ledger_public:
        raise HTTPException(404, "No public proof-of-skill ledger at this address")
    entries = db.query(LedgerEntry).filter_by(profile_id=p.id).order_by(LedgerEntry.id).all()
    skills: dict[int, dict] = {}
    for e in entries:
        s = skills.setdefault(e.skill_id, {"skill": e.skill.name, "slug": e.skill.slug, "category": e.skill.category,
                                           "sfia_code": e.skill.sfia_code, "tier": 0, "entries": []})
        s["tier"] = max(s["tier"], e.tier)
        s["entries"].append({"tier": e.tier, "kind": e.kind, "summary": e.summary, "evidence": e.evidence,
                             "verified_at": e.created_at.isoformat() + "Z", "hash": e.entry_hash})
    for s in skills.values():
        s["tier_name"] = skill_dna.TIER_NAMES[s["tier"]]
    gap = career.gap_analysis(db, p, p.target_role) if p.target_role else None
    return {
        "learner": {"display_name": p.user.display_name, "headline": p.headline, "public_id": p.public_id},
        "target_role": {"title": p.target_role.title, "onet_code": p.target_role.onet_code,
                        "match_score": gap["match_score"], "formula": gap["formula"]} if gap else None,
        "skills": sorted(skills.values(), key=lambda s: (-s["tier"], s["skill"])),
        "projects": [{"name": x.name, "description": x.description, "url": x.url} for x in p.projects],
        "ledger": {"entries": len(entries), "chain_valid": skill_dna.verify_chain(entries),
                   "head_hash": entries[-1].entry_hash if entries else None,
                   "algorithm": "SHA-256 hash chain over each entry and the previous hash"},
        "policy": "Only verified (Tier 1+) evidence appears here. Self-claimed skills, code, hidden tests and private profile data are never shown.",
    }


# ---------------- admin ----------------

admin = require_role("admin")


@router.get("/api/admin/stats")
def admin_stats(_: User = Depends(admin), db: Session = Depends(get_db)):
    roles = Counter(r for (r,) in db.query(User.role))
    agents = Counter()
    errors = Counter()
    for a, st in db.query(AgentExecution.agent, AgentExecution.status):
        agents[a] += 1
        if st != "ok":
            errors[a] += 1
    subs = Counter(s for (s,) in db.query(Submission.status))
    events = Counter(e for (e,) in db.query(WorkflowRun.event))
    return {
        "users": dict(roles),
        "catalog": {"skills": db.query(Skill).count(), "roles": db.query(CareerRole).count(),
                    "missions": db.query(Mission).count(), "resources": db.query(Resource).count()},
        "agents": [{"agent": a, "executions": n, "errors": errors[a]} for a, n in agents.most_common()],
        "events": dict(events),
        "submissions": dict(subs),
        "ledger_entries": db.query(LedgerEntry).count(),
        "integrations": {"llm": llm.engine_label(), "embeddings": llm.embedding_model_name(),
                         "execution": sandbox.engine_name(), "database": db.bind.dialect.name,
                         "vector_search": "pgvector" if db.bind.dialect.name == "postgresql" else "in-process cosine",
                         "queue": "rq" if sandbox.settings.redis_url else "in-process"},
    }


@router.get("/api/admin/users")
def admin_users(_: User = Depends(admin), db: Session = Depends(get_db)):
    out = []
    for u in db.query(User).order_by(User.created_at.desc()).limit(200):
        p = u.profile
        out.append({"id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role,
                    "created_at": u.created_at.isoformat(),
                    "target_role": p.target_role.title if p and p.target_role else None,
                    "verified_skills": sum(1 for ls in p.skills if ls.tier >= 1) if p else 0,
                    "last_active_at": p.last_active_at.isoformat() if p else None})
    return out


@router.get("/api/admin/runs")
def admin_runs(_: User = Depends(admin), db: Session = Depends(get_db)):
    return [run_out(db, r) for r in db.query(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(40)]


@router.post("/api/admin/stall-scan")
async def stall_scan(_: User = Depends(admin)):
    return await run_stall_scan()


async def run_stall_scan(days: int = 3) -> dict:
    from datetime import timedelta

    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(days=days)
        ids = [p.id for p in db.query(LearnerProfile).filter(LearnerProfile.onboarded.is_(True), LearnerProfile.last_active_at < cutoff)]
    finally:
        db.close()
    runs = [await dispatch(pid, "STALLED", {}, background=True) for pid in ids]
    return {"stalled_learners": len(ids), "runs": [r["run_id"] for r in runs]}


# ---------------- websocket ----------------


@router.websocket("/ws")
async def ws(websocket: WebSocket, token: str = ""):
    db = SessionLocal()
    try:
        user = user_from_token(token, db) if token else None
        prof = db.query(LearnerProfile).filter_by(user_id=user.id).first() if user else None
    finally:
        db.close()
    if not prof:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    await manager.connect(prof.id, websocket)
    try:
        await websocket.send_json({"type": "hello", "profile_id": prof.id})
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(prof.id, websocket)
