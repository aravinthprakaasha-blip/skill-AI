from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs import dispatch
from ..models import (
    Assessment,
    CareerRole,
    Certification,
    LearnerProfile,
    MentorMessage,
    Mission,
    ProgressRecord,
    Project,
    Skill,
    Submission,
    User,
    WorkflowRun,
    utcnow,
)
from ..schemas import MentorIn, OnboardIn, PivotIn, ProfileIn, QuizIn, SimulateIn
from ..security import current_user
from ..services import assessments, career, mentor, resources, roadmap, skill_dna
from .common import RateLimiter, run_out, run_summary

router = APIRouter(prefix="/api", tags=["learner"])
mentor_limit = RateLimiter(2.0)


def learner(user: User = Depends(current_user), db: Session = Depends(get_db)) -> LearnerProfile:
    if user.role != "learner":
        raise HTTPException(403, "Learner account required")
    prof = db.query(LearnerProfile).filter_by(user_id=user.id).first()
    if not prof:
        prof = LearnerProfile(user_id=user.id)
        db.add(prof)
        db.commit()
    return prof


def profile_out(p: LearnerProfile) -> dict:
    return {
        "id": p.id, "public_id": p.public_id, "display_name": p.user.display_name, "email": p.user.email,
        "headline": p.headline, "education": p.education,
        "target_role": {"slug": p.target_role.slug, "title": p.target_role.title} if p.target_role else None,
        "timeline_weeks": p.timeline_weeks, "weekly_hours": p.weekly_hours, "github_repos": p.github_repos,
        "ledger_public": p.ledger_public, "onboarded": p.onboarded,
        "projects": [{"id": x.id, "name": x.name, "description": x.description, "url": x.url} for x in p.projects],
        "certifications": [{"id": c.id, "name": c.name, "issuer": c.issuer, "year": c.year} for c in p.certifications],
        "claimed_skills": [ls.skill.slug for ls in p.skills if ls.claimed],
    }


# ---------------- profile ----------------


@router.get("/profile")
def get_profile(p: LearnerProfile = Depends(learner)):
    return profile_out(p)


@router.put("/profile")
def update_profile(body: ProfileIn, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "target_role_slug" in data:
        role = db.query(CareerRole).filter_by(slug=data.pop("target_role_slug")).first()
        if not role:
            raise HTTPException(422, "Unknown career role")
        if p.onboarded and p.target_role_id and role.id != p.target_role_id:
            raise HTTPException(409, "Use the career pivot endpoint to change your goal after onboarding")
        p.target_role_id = role.id
    if "display_name" in data:
        p.user.display_name = data.pop("display_name") or p.user.display_name
    if "projects" in data:
        p.projects = [Project(**x) for x in data.pop("projects")]
    if "certifications" in data:
        p.certifications = [Certification(**x) for x in data.pop("certifications")]
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    if p.onboarded:
        roadmap.reschedule(db, p)
        db.commit()
    return profile_out(p)


@router.post("/profile/onboard")
async def onboard(body: OnboardIn, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    if not p.target_role_id:
        raise HTTPException(422, "Choose a target role first")
    p.onboarded = True
    skill_dna.record_progress(db, p.id, "onboard", {"role": p.target_role.slug})
    db.commit()
    return await dispatch(p.id, "ONBOARD", {"claimed_skills": [s[:60] for s in body.claimed_skills]}, background=True)


@router.post("/profile/pivot")
async def pivot(body: PivotIn, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    role = db.query(CareerRole).filter_by(slug=body.role_slug).first()
    if not role:
        raise HTTPException(422, "Unknown career role")
    if role.id == p.target_role_id:
        raise HTTPException(409, "That is already your target role")
    skill_dna.record_progress(db, p.id, "pivot", {"to": role.slug})
    db.commit()
    return await dispatch(p.id, "PIVOT_GOAL", {"role_slug": role.slug}, background=True)


@router.post("/profile/checkin")
async def stall_check(p: LearnerProfile = Depends(learner)):
    """Ask the orchestrator to evaluate inactivity (STALLED). No-op if the learner is active."""
    return await dispatch(p.id, "STALLED", {}, background=False)


# ---------------- skills ----------------


@router.get("/skills")
def skill_matrix(p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    rows = skill_dna.matrix(db, p)
    return {"tiers": skill_dna.TIER_NAMES, "skills": rows}


@router.get("/skills/{skill_id}/quiz")
def get_quiz(skill_id: int, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    skill = db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    return assessments.public_quiz(db, skill)


@router.post("/skills/{skill_id}/quiz")
async def submit_quiz(skill_id: int, body: QuizIn, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    skill = db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    try:
        a = assessments.grade(db, p.id, skill, body.answers)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    skill_dna.record_progress(db, p.id, "quiz", {"skill": skill.slug, "score": a.score, "passed": a.passed, "attempt": a.attempt_no})
    db.commit()
    run = await dispatch(p.id, "ASSESSMENT_PASSED" if a.passed else "ASSESSMENT_FAILED",
                         {"kind": "quiz", "assessment_id": a.id})
    return {"assessment_id": a.id, "score": a.score, "passed": a.passed, "attempt": a.attempt_no,
            "detail": a.detail, "run": run_summary(run)}


# ---------------- careers ----------------


@router.get("/careers/roles")
def roles(p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    return career.role_scores(db, p)


@router.get("/careers/gap")
def gap(role: str | None = None, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    r = db.query(CareerRole).filter_by(slug=role).first() if role else p.target_role
    if not r:
        raise HTTPException(404, "Role not found")
    return career.gap_analysis(db, p, r)


@router.post("/careers/simulate")
def simulate(body: SimulateIn, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    r = db.query(CareerRole).filter_by(slug=body.role_slug).first()
    if not r:
        raise HTTPException(404, "Role not found")
    return career.gap_analysis(db, p, r, body.overrides)


@router.get("/careers/dag")
def dag(role: str | None = None, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    r = db.query(CareerRole).filter_by(slug=role).first() if role else p.target_role
    if not r:
        raise HTTPException(404, "Role not found")
    return roadmap.build_dag(db, p, r)


# ---------------- roadmap ----------------


@router.get("/roadmap")
def get_roadmap(p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    return roadmap.serialize(db, roadmap.active_roadmap(db, p.id))


@router.get("/roadmap/history")
def roadmap_history(p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    from ..models import Roadmap

    return [{"id": r.id, "role": r.role.title, "status": r.status, "created_at": r.created_at.isoformat(), "summary": r.summary}
            for r in db.query(Roadmap).filter_by(profile_id=p.id).order_by(Roadmap.id.desc())]


@router.get("/resources/search")
async def search_resources(q: str, skill_id: int | None = None, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    return await resources.search(db, q[:300], skill_id, k=6)


# ---------------- workflow runs ----------------


@router.get("/runs")
def list_runs(p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    runs = db.query(WorkflowRun).filter_by(profile_id=p.id).order_by(WorkflowRun.created_at.desc()).limit(30).all()
    return [run_out(db, r) for r in runs]


@router.get("/runs/{run_id}")
def get_run(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.get(WorkflowRun, run_id)
    prof = db.query(LearnerProfile).filter_by(user_id=user.id).first()
    if not run or (user.role != "admin" and (not prof or run.profile_id != prof.id)):
        raise HTTPException(404, "Run not found")
    return run_out(db, run)


# ---------------- mentor ----------------


@router.get("/mentor/messages")
def mentor_messages(mission_id: int | None = None, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    q = db.query(MentorMessage).filter_by(profile_id=p.id)
    if mission_id:
        q = q.filter(MentorMessage.mission_id == mission_id)
    rows = q.order_by(MentorMessage.id.desc()).limit(50).all()
    return [{"id": m.id, "role": m.role, "content": m.content, "meta": m.meta, "mission_id": m.mission_id,
             "created_at": m.created_at.isoformat()} for m in reversed(rows)]


@router.post("/mentor/chat")
async def mentor_chat(body: MentorIn, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    mentor_limit.check(p.id)
    m = db.get(Mission, body.mission_id) if body.mission_id else None
    history = [{"role": x.role, "content": x.content} for x in
               db.query(MentorMessage).filter_by(profile_id=p.id, mission_id=body.mission_id).order_by(MentorMessage.id.desc()).limit(6)][::-1]
    ctx = {"mission_title": m.title if m else "General question", "brief": m.brief if m else "", "language": body.language,
           "code": body.code, "message": body.message, "test_report": body.test_report, "ast_report": body.ast_report,
           "history": history}
    out = await mentor.mentor_reply(ctx)
    if body.message:
        db.add(MentorMessage(profile_id=p.id, mission_id=body.mission_id, role="learner", content=body.message))
    content = f"{out['reply']}\n\n{out['guiding_question']}".strip()
    db.add(MentorMessage(profile_id=p.id, mission_id=body.mission_id, role="mentor", content=content, meta={"engine": out["engine"]}))
    p.last_active_at = utcnow()
    db.commit()
    return {"reply": out["reply"], "guiding_question": out["guiding_question"], "engine": out["engine"]}


# ---------------- analytics ----------------


def _streak(days: set) -> tuple[int, int]:
    if not days:
        return 0, 0
    today = utcnow().date()
    cur, d = 0, today if today in days else today - timedelta(days=1)
    while d in days:
        cur += 1
        d -= timedelta(days=1)
    best, run, prev = 0, 0, None
    for day in sorted(days):
        run = run + 1 if prev and (day - prev).days == 1 else 1
        best, prev = max(best, run), day
    return cur, best


@router.get("/analytics")
def analytics(p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    matrix = skill_dna.matrix(db, p)
    by_cat: dict[str, list] = defaultdict(list)
    for s in matrix:
        by_cat[s["category"]].append(s)
    radar = [{"category": c, "verified": round(sum(x["tier"] for x in xs) / len(xs), 2),
              "required": round(sum((x["required_tier"] or 0) for x in xs) / len(xs), 2)} for c, xs in sorted(by_cat.items())]
    tier_counts = {t: sum(1 for s in matrix if s["tracked"] and s["tier"] == t) for t in range(4)}

    readiness = [{"at": r.created_at.isoformat(), "role": r.value.get("role"), "score": r.value.get("score")}
                 for r in db.query(ProgressRecord).filter_by(profile_id=p.id, kind="readiness").order_by(ProgressRecord.id)]
    quizzes = db.query(Assessment).filter_by(profile_id=p.id).order_by(Assessment.id).all()
    subs = db.query(Submission).filter_by(profile_id=p.id).order_by(Submission.id).all()

    first_attempts = [s for s in subs if s.attempt_no == 1 and s.status not in ("queued", "running", "error")]
    first_q = [a for a in quizzes if a.attempt_no == 1]
    passed_missions = {s.mission_id for s in subs if s.tests_passed and s.ast_report.get("passed")}
    verified_missions = {s.mission_id for s in subs if s.status == "verified"}
    attempted = {s.mission_id for s in subs}
    rm = roadmap.serialize(db, roadmap.active_roadmap(db, p.id))
    days = {r.day for r in db.query(ProgressRecord).filter_by(profile_id=p.id)}
    cur, best = _streak(days)
    gap = career.gap_analysis(db, p, p.target_role) if p.target_role else None
    return {
        "readiness": gap["match_score"] if gap else None,
        "role": gap["role"]["title"] if gap else None,
        "readiness_history": readiness,
        "radar": radar,
        "tier_counts": tier_counts,
        "missions": {"attempted": len(attempted), "passed": len(passed_missions), "verified": len(verified_missions),
                     "total": db.query(Mission).count(), "submissions": len(subs)},
        "first_attempt": {
            "missions_rate": round(100 * sum(1 for s in first_attempts if s.tests_passed) / len(first_attempts), 1) if first_attempts else None,
            "missions_n": len(first_attempts),
            "quizzes_rate": round(100 * sum(1 for a in first_q if a.passed) / len(first_q), 1) if first_q else None,
            "quizzes_n": len(first_q),
        },
        "assessments": [{"at": a.created_at.isoformat(), "skill": a.skill.name, "score": a.score, "passed": a.passed,
                         "attempt": a.attempt_no} for a in quizzes],
        "submissions": [{"at": s.created_at.isoformat(), "mission": s.mission.title, "status": s.status,
                         "attempt": s.attempt_no, "language": s.language,
                         "hidden": f"{s.test_report.get('hidden', {}).get('passed_count', 0)}/{s.test_report.get('hidden', {}).get('total', 0)}"}
                        for s in subs],
        "roadmap_progress": rm["progress"] if rm else None,
        "streak": {"current": cur, "best": best, "active_days": len(days)},
    }
