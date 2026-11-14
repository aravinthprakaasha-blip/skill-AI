from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs import dispatch
from ..models import LearnerProfile, Mission, Submission, VivaSession, utcnow
from ..schemas import CodeIn, VivaIn
from ..services import mentor, sandbox, skill_dna, static_analysis
from .common import RateLimiter, run_summary
from .learner import learner

router = APIRouter(prefix="/api", tags=["missions"])
run_limit = RateLimiter(1.5)
submit_limit = RateLimiter(4.0)


def mission_out(m: Mission, full: bool = False) -> dict:
    out = {"id": m.id, "slug": m.slug, "title": m.title, "kind": m.kind, "difficulty": m.difficulty,
           "skill": {"id": m.skill.id, "slug": m.skill.slug, "name": m.skill.name},
           "languages": list(m.languages.keys()), "est_hours": m.est_hours,
           "grants_tier": 3 if m.kind == "applied" else 2}
    if full:
        out.update({
            "brief": m.brief, "docs": m.docs,
            "starters": {k: v["starter"] for k, v in m.languages.items()},
            "visible_tests": [{"name": t["name"], "input": t["call"], "expected": t["expected"]} for t in m.visible_tests],
            "hidden_test_count": len(m.hidden_tests),  # hidden test contents never leave the server
            "rules": {k: v for k, v in m.ast_rules.items()},
            "limits": {"time_s": sandbox.settings.exec_time_limit_s, "memory_kb": sandbox.settings.exec_memory_limit_kb},
            "execution_engine": sandbox.engine_name(),
        })
    return out


def _mission(db: Session, mission_id: int) -> Mission:
    m = db.get(Mission, mission_id)
    if not m:
        raise HTTPException(404, "Mission not found")
    return m


def submission_out(db: Session, s: Submission) -> dict:
    viva = db.query(VivaSession).filter_by(submission_id=s.id).first()
    return {
        "id": s.id, "mission_id": s.mission_id, "mission": s.mission.title, "mission_kind": s.mission.kind,
        "language": s.language, "status": s.status, "attempt": s.attempt_no, "tests_passed": s.tests_passed,
        "test_report": s.test_report, "ast_report": s.ast_report, "ai_review": s.ai_review,
        "created_at": s.created_at.isoformat(), "code": s.code,
        "viva": {"id": viva.id, "status": viva.status, "questions": mentor.public_questions(viva.questions),
                 "evaluation": {k: viva.evaluation.get(k) for k in ("passed", "deterministic_pass", "llm_pass", "engine", "rule", "answers", "question_engine")}}
        if viva else None,
    }


@router.get("/missions")
def list_missions(p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    subs = db.query(Submission).filter_by(profile_id=p.id).all()
    best: dict[int, str] = {}
    rank = {"verified": 5, "awaiting_viva": 4, "passed_tests": 4, "viva_failed": 3, "failed_audit": 2, "failed_tests": 1}
    for s in subs:
        if rank.get(s.status, 0) >= rank.get(best.get(s.mission_id, ""), 0):
            best[s.mission_id] = s.status
    return [{**mission_out(m), "best_status": best.get(m.id)} for m in db.query(Mission).order_by(Mission.kind, Mission.id)]


@router.get("/missions/{mission_id}")
def get_mission(mission_id: int, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    m = _mission(db, mission_id)
    subs = db.query(Submission).filter_by(profile_id=p.id, mission_id=m.id).order_by(Submission.id.desc()).limit(10)
    return {**mission_out(m, full=True),
            "submissions": [{"id": s.id, "status": s.status, "attempt": s.attempt_no, "language": s.language,
                             "created_at": s.created_at.isoformat()} for s in subs]}


@router.post("/missions/{mission_id}/run")
async def run_visible(mission_id: int, body: CodeIn, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    """Practice run: visible tests + static audit only. Never changes Skill DNA."""
    run_limit.check(p.id)
    m = _mission(db, mission_id)
    if body.language not in m.languages:
        raise HTTPException(422, f"This mission does not support {body.language}")
    cfg = m.languages[body.language]
    audit = static_analysis.audit(body.code, body.language, m.ast_rules, cfg.get("names"))
    blocked = [v for v in audit["violations"] if v["rule"] in ("banned_import", "banned_call", "banned_name", "syntax")]
    if blocked:
        tests = {"status": "skipped", "passed": False, "passed_count": 0, "total": len(m.visible_tests), "results": [],
                 "stdout": "", "stderr": "Execution skipped: " + "; ".join(v["message"] for v in blocked[:3]),
                 "engine": sandbox.engine_name()}
    else:
        tests = await sandbox.run_tests(body.language, body.code, m.visible_tests, cfg, reveal=True)
    p.last_active_at = utcnow()
    db.commit()
    return {"tests": tests, "audit": audit}


@router.post("/missions/{mission_id}/submit")
async def submit(mission_id: int, body: CodeIn, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    submit_limit.check(p.id)
    m = _mission(db, mission_id)
    if body.language not in m.languages:
        raise HTTPException(422, f"This mission does not support {body.language}")
    n = db.query(Submission).filter_by(profile_id=p.id, mission_id=m.id).count()
    s = Submission(profile_id=p.id, mission_id=m.id, language=body.language, code=body.code, attempt_no=n + 1)
    db.add(s)
    skill_dna.record_progress(db, p.id, "submission", {"mission": m.slug, "attempt": n + 1})
    db.commit()
    run = await dispatch(p.id, "SUBMIT_CODE", {"submission_id": s.id}, background=True)
    s.run_id = run["run_id"]
    db.commit()
    return {"submission_id": s.id, **run}


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: int, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    s = db.get(Submission, submission_id)
    if not s or s.profile_id != p.id:
        raise HTTPException(404, "Submission not found")
    return submission_out(db, s)


@router.get("/submissions")
def list_submissions(p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    rows = db.query(Submission).filter_by(profile_id=p.id).order_by(Submission.id.desc()).limit(30)
    return [{"id": s.id, "mission": s.mission.title, "mission_id": s.mission_id, "status": s.status,
             "attempt": s.attempt_no, "language": s.language, "created_at": s.created_at.isoformat()} for s in rows]


@router.get("/viva")
def list_vivas(p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    rows = db.query(VivaSession).filter_by(profile_id=p.id).order_by(VivaSession.id.desc()).limit(30)
    return [{"id": v.id, "submission_id": v.submission_id, "mission": v.submission.mission.title,
             "mission_id": v.submission.mission_id, "language": v.submission.language, "status": v.status,
             "questions": mentor.public_questions(v.questions), "answers": v.answers,
             "evaluation": {k: v.evaluation.get(k) for k in ("passed", "deterministic_pass", "llm_pass", "engine", "rule", "answers", "question_engine")},
             "created_at": v.created_at.isoformat()} for v in rows]


@router.post("/viva/{viva_id}/answer")
async def answer_viva(viva_id: int, body: VivaIn, p: LearnerProfile = Depends(learner), db: Session = Depends(get_db)):
    viva = db.get(VivaSession, viva_id)
    if not viva or viva.profile_id != p.id:
        raise HTTPException(404, "Viva not found")
    if viva.status != "pending":
        raise HTTPException(409, "This viva is already complete. Resubmit the mission for a new one.")
    if len(body.answers) != len(viva.questions):
        raise HTTPException(422, f"Answer all {len(viva.questions)} questions")
    sub = viva.submission
    ev = await mentor.evaluate_viva(sub.code, sub.language, viva.questions, body.answers)
    viva.answers = body.answers
    viva.evaluation = {**viva.evaluation, **ev}
    viva.status = "passed" if ev["passed"] else "failed"
    if not ev["passed"]:
        sub.status = "viva_failed"
    skill_dna.record_progress(db, p.id, "viva", {"mission": sub.mission.slug, "passed": ev["passed"]})
    db.commit()
    run = await dispatch(p.id, "ASSESSMENT_PASSED" if ev["passed"] else "ASSESSMENT_FAILED", {"kind": "viva", "viva_id": viva.id})
    return {"passed": ev["passed"], "evaluation": ev, "run": run_summary(run)}
