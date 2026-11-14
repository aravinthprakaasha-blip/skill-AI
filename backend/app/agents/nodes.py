"""Agent task handlers. Each returns a structured JSON-serialisable dict that is written to the
shared state (`outputs[agent]`) and persisted to `agent_executions`. Later agents read earlier
agents' outputs from that shared state - they do not call each other directly."""
import re

import httpx

from ..config import get_settings
from ..db import session_scope
from ..models import (
    Assessment,
    CareerRole,
    LearnerProfile,
    MentorMessage,
    Skill,
    Submission,
    VivaSession,
    utcnow,
)
from ..services import career, mentor, resources, review, roadmap, sandbox, skill_dna, static_analysis
from .state import AgentState

settings = get_settings()


def _profile(db, state: AgentState) -> LearnerProfile:
    prof = db.get(LearnerProfile, state["profile_id"])
    if not prof:
        raise ValueError("Unknown learner profile")
    return prof


def match_skill(skills: list[Skill], text: str) -> Skill | None:
    norm = re.sub(r"[^a-z0-9+#.]+", " ", text.lower()).strip()
    for s in skills:
        if norm in (s.slug, s.name.lower(), s.slug.replace("-", " ")) or norm in [a.lower() for a in s.aliases]:
            return s
    return None


def _say(db, profile_id: str, content: str, meta: dict, mission_id: int | None = None) -> None:
    db.add(MentorMessage(profile_id=profile_id, mission_id=mission_id, role="mentor", content=content, meta=meta))


# ============================ Skill Detective ============================


async def _github_languages(repos: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    async with httpx.AsyncClient(timeout=6) as client:
        for url in repos[:5]:
            m = re.match(r"https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url.strip())
            if not m:
                continue
            try:
                r = await client.get(f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/languages")
                if r.status_code == 200:
                    out[url] = list(r.json().keys())[:6]
            except httpx.HTTPError:
                continue
    return out


async def skill_detective(state: AgentState, task: str) -> dict:
    payload = state.get("payload", {})
    github: dict = {}
    if task == "profile_scan" and settings.github_enrichment:
        with session_scope() as db:
            repos = list(_profile(db, state).github_repos or [])
        github = await _github_languages(repos)

    with session_scope() as db:
        prof = _profile(db, state)
        if task == "profile_scan":
            skills = db.query(Skill).all()
            existing = {ls.skill_id for ls in prof.skills if ls.claimed}
            recorded, unknown = [], []
            for raw in payload.get("claimed_skills", []):
                s = match_skill(skills, str(raw))
                if not s:
                    unknown.append(str(raw)[:60])
                elif s.id not in existing:
                    skill_dna.add_evidence(db, prof.id, s.id, tier=0, kind="claim",
                                           summary="Self-reported during onboarding (unverified)")
                    existing.add(s.id)
                    recorded.append(s.slug)
            for url, langs in github.items():
                for lang in langs:
                    s = match_skill(skills, lang)
                    if s:
                        skill_dna.add_evidence(db, prof.id, s.id, tier=0, kind="github",
                                               summary=f"Language detected in {url} (signal only, unverified)")
            db.flush()
            db.refresh(prof)
            dna = [{"skill": ls.skill.slug, "tier": ls.tier, "claimed": ls.claimed} for ls in prof.skills]
            return {
                "task": task,
                "claims_recorded": recorded,
                "unrecognised_claims": unknown,
                "github_signals": github,
                "skill_dna": dna,
                "verified_count": sum(1 for d in dna if d["tier"] >= 1),
                "unverified_claims": [d["skill"] for d in dna if d["tier"] == 0],
                "note": "Claims are Tier 0 and contribute nothing to match scores until verified.",
            }

        if task == "record_evidence":
            kind = payload.get("kind")
            if kind == "quiz":
                a = db.get(Assessment, payload["assessment_id"])
                if not a or a.profile_id != prof.id or not a.passed:
                    return {"task": task, "granted": False, "reason": "No passing quiz assessment found"}
                d = a.detail
                res = skill_dna.add_evidence(
                    db, prof.id, a.skill_id, tier=1, kind="quiz",
                    summary=f"Concept quiz passed: {d.get('correct')}/{d.get('total')} ({a.score:.0f}%)",
                    data={"assessment_id": a.id, "score": a.score, "attempt": a.attempt_no},
                    ref_type="assessment", ref_id=a.id,
                    public_evidence={"score_pct": a.score, "questions": d.get("total"), "attempt": a.attempt_no},
                )
                return {"task": task, "granted": True, "evidence_kind": "quiz", "skill": a.skill.slug, **res}
            if kind == "submission":
                sub = db.get(Submission, payload["submission_id"])
                ok = bool(sub and sub.profile_id == prof.id and sub.tests_passed and sub.ast_report.get("passed"))
                if not ok:
                    return {"task": task, "granted": False, "reason": "Submission did not pass tests and audit"}
                hidden = sub.test_report.get("hidden", {})
                res = skill_dna.add_evidence(
                    db, prof.id, sub.mission.skill_id, tier=2, kind="tests",
                    summary=f"{sub.mission.title}: {hidden.get('passed_count')}/{hidden.get('total')} hidden tests passed, static audit clean",
                    data={"submission_id": sub.id, "language": sub.language, "attempt": sub.attempt_no},
                    ref_type="submission", ref_id=sub.id,
                    public_evidence={
                        "mission": sub.mission.title, "language": sub.language,
                        "hidden_tests_passed": hidden.get("passed_count"), "hidden_tests_total": hidden.get("total"),
                        "audit_engine": sub.ast_report.get("engine"), "audit_violations": 0,
                        "execution_engine": hidden.get("engine"), "attempt": sub.attempt_no,
                    },
                )
                if sub.mission.kind == "coding":
                    sub.status = "verified"
                return {"task": task, "granted": True, "evidence_kind": "tests", "skill": sub.mission.skill.slug,
                        "mission_kind": sub.mission.kind, "tier3_pending_viva": sub.mission.kind == "applied", **res}
            if kind == "viva":
                viva = db.get(VivaSession, payload["viva_id"])
                sub = viva.submission if viva else None
                # Tier 3 guard: deterministic tests + AST audit + grounded viva. Never LLM judgment alone.
                checks = {
                    "owns_submission": bool(sub and sub.profile_id == prof.id),
                    "applied_mission": bool(sub and sub.mission.kind == "applied"),
                    "hidden_tests_passed": bool(sub and sub.tests_passed),
                    "ast_audit_passed": bool(sub and sub.ast_report.get("passed")),
                    "viva_passed": bool(viva and viva.status == "passed"),
                    "viva_grounding_passed": bool(viva and viva.evaluation.get("deterministic_pass")),
                }
                if not all(checks.values()):
                    return {"task": task, "granted": False, "checks": checks, "reason": "Tier 3 requirements not all met"}
                res = skill_dna.add_evidence(
                    db, prof.id, sub.mission.skill_id, tier=3, kind="viva",
                    summary=f"{sub.mission.title}: applied project verified (tests + AST audit + Micro-Viva)",
                    data={"submission_id": sub.id, "viva_id": viva.id, "checks": checks},
                    ref_type="viva", ref_id=viva.id,
                    public_evidence={"mission": sub.mission.title, "language": sub.language,
                                     "viva_questions": len(viva.questions), "viva_engine": viva.evaluation.get("engine"),
                                     "checks": checks},
                )
                sub.status = "verified"
                return {"task": task, "granted": True, "evidence_kind": "viva", "skill": sub.mission.skill.slug,
                        "checks": checks, **res}
            return {"task": task, "granted": False, "reason": f"Unknown evidence kind {kind!r}"}

        if task == "transferable_skills":
            new_role = db.query(CareerRole).filter_by(slug=payload.get("role_slug")).first()
            if not new_role:
                raise ValueError("Unknown target role")
            tiers = skill_dna.tiers(db, prof.id)
            req = {r.skill_id: r for r in new_role.requirements}
            verified = [ls for ls in prof.skills if ls.tier >= 1]
            return {
                "task": task,
                "from_role": prof.target_role.slug if prof.target_role else None,
                "to_role": new_role.slug,
                "transferable": [{"skill": ls.skill.slug, "tier": ls.tier, "required_tier": req[ls.skill_id].required_tier}
                                 for ls in verified if ls.skill_id in req],
                "preserved_not_required": [{"skill": ls.skill.slug, "tier": ls.tier} for ls in verified if ls.skill_id not in req],
                "verified_total": len(verified),
                "note": "All verified evidence is preserved; nothing is deleted on a pivot.",
                "already_meets": [r.skill.slug for r in new_role.requirements if tiers.get(r.skill_id, 0) >= r.required_tier],
            }

        if task == "activity_check":
            days = (utcnow() - prof.last_active_at).days
            rm = roadmap.active_roadmap(db, prof.id)
            nxt = next((it for it in rm.items if it.status == "pending"), None) if rm else None
            return {"task": task, "days_inactive": days, "stalled": days >= 3,
                    "next_item": {"id": nxt.id, "skill": nxt.skill.slug, "step": nxt.step, "skill_id": nxt.skill_id} if nxt else None}
    raise ValueError(f"skill_detective: unknown task {task}")


# ============================ Career Architect ============================


async def career_architect(state: AgentState, task: str) -> dict:
    payload = state.get("payload", {})
    with session_scope() as db:
        prof = _profile(db, state)
        previous = None
        if state["event"] == "PIVOT_GOAL":
            new_role = db.query(CareerRole).filter_by(slug=payload.get("role_slug")).first()
            if not new_role:
                raise ValueError("Unknown target role")
            if prof.target_role:
                previous = {"role": prof.target_role.slug,
                            "match_score": career.gap_analysis(db, prof, prof.target_role)["match_score"]}
            prof.target_role_id = new_role.id
            db.flush()
            db.refresh(prof)
        role = prof.target_role
        if not role:
            return {"task": task, "match_score": None, "reason": "No target role set"}
        g = career.gap_analysis(db, prof, role)
        skill_dna.record_progress(db, prof.id, "readiness", {"role": role.slug, "score": g["match_score"]})
        return {
            "task": task,
            "role": role.slug,
            "role_title": role.title,
            "onet_code": role.onet_code,
            "sfia_level": role.sfia_level,
            "match_score": g["match_score"],
            "formula": g["formula"],
            "weighted_points": g["weighted_points"],
            "max_points": g["max_points"],
            "critical_missing": [r["slug"] for r in g["critical_missing"]],
            "gaps": [{"skill": r["slug"], "verified_tier": r["verified_tier"], "required_tier": r["required_tier"],
                      "weight": r["weight"]} for r in g["gaps"]],
            "recommended": [r["slug"] for r in g["recommended"]],
            "previous": previous,
        }


# ============================ Learning Strategist ============================


async def learning_strategist(state: AgentState, task: str) -> dict:
    outputs = state.get("outputs", {})
    with session_scope() as db:
        prof = _profile(db, state)
        if task == "generate_roadmap":
            if not prof.target_role:
                return {"task": task, "items_created": 0, "reason": "No target role set"}
            reason = "pivot" if state["event"] == "PIVOT_GOAL" else "onboard"
            diff = roadmap.generate(db, prof, prof.target_role, reason)
            dag = roadmap.build_dag(db, prof, prof.target_role)
            return {"task": task, **diff, "dag": {"nodes": len(dag["nodes"]), "edges": len(dag["edges"]),
                                                    "topological_order": dag["order"]}}
        if task == "update_progress":
            done = roadmap.refresh_progress(db, prof)
            rm = roadmap.active_roadmap(db, prof.id)
            nxt = next((it for it in rm.items if it.status == "pending"), None) if rm else None
            return {"task": task, "items_completed": done,
                    "next_item": {"id": nxt.id, "skill": nxt.skill.name, "step": nxt.step,
                                  "mission_id": nxt.mission_id, "skill_id": nxt.skill_id} if nxt else None,
                    "summary": rm.summary if rm else None}
        if task == "add_remediation":
            diag = outputs.get("ai_mentor", {})
            scout = outputs.get("resource_scout", {})
            if not diag.get("skill_id"):
                return {"task": task, "added": False, "reason": "No diagnosis available"}
            res = roadmap.add_remediation(
                db, prof, diag["skill_id"], diag.get("target_tier", 1),
                f"Review before retrying: {diag.get('diagnosis', '')}",
                [r["id"] for r in scout.get("resources", [])],
            )
            return {"task": task, "added": bool(res), **(res or {}), "skill_id": diag["skill_id"],
                    "resources_attached": len(scout.get("resources", []))}
        if task == "rebalance":
            res = roadmap.reschedule(db, prof)
            return {"task": task, **(res or {"reason": "No active roadmap"})}
    raise ValueError(f"learning_strategist: unknown task {task}")


# ============================ Resource Scout ============================


async def resource_scout(state: AgentState, task: str) -> dict:
    outputs = state.get("outputs", {})
    with session_scope() as db:
        prof = _profile(db, state)
        if task == "attach_resources":
            rm = roadmap.active_roadmap(db, prof.id)
            attached = []
            for it in (rm.items if rm else []):
                if it.status != "pending" or it.resource_ids:
                    continue
                focus = {"concept": "concepts fundamentals guide", "coding": "practice examples reference",
                         "applied": "building a project best practices"}.get(it.step, "review")
                hits = await resources.search(db, f"{it.skill.name} {focus}. {it.skill.description}", it.skill_id, k=3)
                it.resource_ids = [h["id"] for h in hits]
                attached.append({"item_id": it.id, "skill": it.skill.slug, "step": it.step,
                                 "resources": [{"id": h["id"], "title": h["title"], "score": h["score"]} for h in hits]})
            return {"task": task, "items_enriched": len(attached), "attachments": attached[:12],
                    "retrieval": "pgvector" if settings.is_postgres else "in-process cosine"}
        if task == "find_remediation":
            diag = outputs.get("ai_mentor", {})
            query = diag.get("focus_query") or diag.get("diagnosis") or "fundamentals"
            hits = await resources.search(db, query, diag.get("skill_id"), k=3)
            return {"task": task, "query": query, "resources": hits,
                    "retrieval": "pgvector" if settings.is_postgres else "in-process cosine"}
    raise ValueError(f"resource_scout: unknown task {task}")


# ============================ Skill Validator ============================

_BLOCKING = {"banned_import", "banned_call", "banned_name", "syntax"}


async def skill_validator(state: AgentState, task: str) -> dict:
    sid = state["payload"]["submission_id"]
    with session_scope() as db:
        sub = db.get(Submission, sid)
        if not sub or sub.profile_id != state["profile_id"]:
            raise ValueError("Unknown submission")
        sub.status = "running"
        m = sub.mission
        code, lang, cfg = sub.code, sub.language, m.languages[sub.language]
        rules, visible_tests, hidden_tests = m.ast_rules, m.visible_tests, m.hidden_tests
        title, kind, skill_id, attempt = m.title, m.kind, m.skill_id, sub.attempt_no

    # Engine 1: static analysis (runs first; unsafe code is never executed)
    audit = static_analysis.audit(code, lang, rules, cfg.get("names"))
    blocked = [v for v in audit["violations"] if v["rule"] in _BLOCKING]

    # Engine 2: deterministic hidden tests in the sandbox
    if blocked:
        skipped = {"status": "skipped", "passed": False, "passed_count": 0, "results": [],
                   "stderr": "Execution skipped: static audit blocked this submission.", "engine": sandbox.engine_name()}
        visible, hidden = {**skipped, "total": len(visible_tests)}, {**skipped, "total": len(hidden_tests)}
    else:
        visible = await sandbox.run_tests(lang, code, visible_tests, cfg, reveal=True)
        hidden = await sandbox.run_tests(lang, code, hidden_tests, cfg, reveal=False)
    tests_passed = bool(visible["passed"] and hidden["passed"])

    # Engine 3: AI review (advisory)
    ai = await review.ai_review(code, lang, title, audit) if not blocked else {"engine": "skipped"}

    if "unavailable" in (visible["status"], hidden["status"]):
        verdict = "error"
    elif not tests_passed:
        verdict = "audit_failed" if blocked else "tests_failed"
    elif not audit["passed"]:
        verdict = "audit_failed"
    else:
        verdict = "passed"

    with session_scope() as db:
        sub = db.get(Submission, sid)
        sub.tests_passed = tests_passed
        sub.test_report = {"visible": visible, "hidden": hidden}
        sub.ast_report = audit
        sub.ai_review = ai
        sub.status = {"passed": "passed_tests", "tests_failed": "failed_tests", "audit_failed": "failed_audit",
                      "error": "error"}[verdict]
    return {
        "task": task, "submission_id": sid, "verdict": verdict, "mission_kind": kind, "skill_id": skill_id,
        "language": lang, "attempt": attempt, "first_attempt": attempt == 1,
        "tests": {"visible": f"{visible['passed_count']}/{visible['total']}",
                  "hidden": f"{hidden['passed_count']}/{hidden['total']}", "status": hidden["status"],
                  "engine": hidden.get("engine"), "time_ms": hidden.get("time_ms")},
        "audit": {"engine": audit["engine"], "passed": audit["passed"], "violations": audit["violations"][:5],
                  "unmet": [r["rule"] for r in audit["required"] if not r["satisfied"]]},
        "review": {k: ai.get(k) for k in ("engine", "readability", "complexity", "modularity", "practices")},
    }


# ============================ AI Mentor ============================


async def ai_mentor(state: AgentState, task: str) -> dict:
    outputs, payload = state.get("outputs", {}), state.get("payload", {})
    arch, strat = outputs.get("career_architect", {}), outputs.get("learning_strategist", {})

    if task == "brief":
        det = outputs.get("skill_detective", {})
        lines = [f"Your verified match for {arch.get('role_title')} is {arch.get('match_score')}%."]
        if state["event"] == "PIVOT_GOAL":
            keep = det.get("transferable", [])
            lines.append(f"{len(keep)} verified skill(s) transfer to the new role; "
                         f"{len(strat.get('archived', []))} task(s) from your old plan were archived and "
                         f"{len(strat.get('carried', []))} carried over.")
        elif det.get("unverified_claims"):
            lines.append(f"{len(det['unverified_claims'])} claimed skill(s) are still unverified and count as zero until you prove them.")
        if arch.get("critical_missing"):
            lines.append("Critical gaps: " + ", ".join(arch["critical_missing"]) + ".")
        lines.append(f"Your roadmap has {strat.get('items_created', 0)} task(s), about {strat.get('total_hours', 0)} hours "
                     f"({strat.get('weeks_needed', 0)} week(s) at {strat.get('weekly_hours', '?')} h/week), which "
                     f"{'fits' if strat.get('fits_timeline') else 'exceeds'} your {strat.get('timeline_weeks', '?')}-week timeline.")
        if strat.get("skills_in_order"):
            lines.append(f"Start with {strat['skills_in_order'][0]}.")
        msg = " ".join(lines)
        with session_scope() as db:
            _say(db, state["profile_id"], msg, {"task": task, "event": state["event"]})
        return {"task": task, "message": msg, "engine": "deterministic-template"}

    if task == "debrief":
        det = outputs.get("skill_detective", {})
        nxt = strat.get("next_item")
        if det.get("granted"):
            msg = (f"Verified: {det.get('skill')} is now Tier {det.get('tier_after')}. "
                   f"Role match is {arch.get('match_score')}%.")
        else:
            msg = f"No tier change was recorded ({det.get('reason', 'requirements not met')})."
        msg += f" Next up: {nxt['skill']} ({nxt['step']})." if nxt else " Your roadmap is complete."
        with session_scope() as db:
            _say(db, state["profile_id"], msg, {"task": task})
        return {"task": task, "message": msg, "engine": "deterministic-template"}

    if task == "start_viva":
        sid = payload["submission_id"]
        with session_scope() as db:
            sub = db.get(Submission, sid)
            code, lang, title, audit, mission_id = sub.code, sub.language, sub.mission.title, sub.ast_report, sub.mission_id
        gen = await mentor.generate_viva(code, lang, title, audit)
        with session_scope() as db:
            viva = db.query(VivaSession).filter_by(submission_id=sid).first()
            if not viva:
                viva = VivaSession(submission_id=sid, profile_id=state["profile_id"], questions=gen["questions"],
                                   evaluation={"question_engine": gen["engine"]})
                db.add(viva)
            db.get(Submission, sid).status = "awaiting_viva"
            db.flush()
            vid = viva.id
            _say(db, state["profile_id"], "Tests and audit passed. Answer two questions about your own code to earn Tier 3.",
                 {"task": task, "viva_id": vid}, mission_id)
        return {"task": task, "viva_id": vid, "engine": gen["engine"], "questions": mentor.public_questions(gen["questions"]),
                "note": "Tier 3 is granted only after this viva passes."}

    if task == "remediate":
        ctx: dict = {"message": ""}
        skill_id, target_tier, mission_id, skill_name = None, 1, None, ""
        with session_scope() as db:
            if payload.get("kind") == "quiz":
                a = db.get(Assessment, payload["assessment_id"])
                skill_id, target_tier, skill_name = a.skill_id, 1, a.skill.name
                missed = [q["prompt"] for q in a.detail.get("questions", []) if not q.get("correct")]
                diagnosis = f"Quiz on {skill_name} scored {a.score:.0f}%; missed: " + "; ".join(m[:90] for m in missed[:3])
                out = {"engine": "deterministic-template", "reply": diagnosis,
                       "guiding_question": "For each missed question, can you explain why the correct option is right?"}
                focus = f"{skill_name} " + " ".join(missed[:2])
            elif payload.get("kind") == "viva":
                viva = db.get(VivaSession, payload["viva_id"])
                sub = viva.submission
                skill_id, target_tier, mission_id, skill_name = sub.mission.skill_id, 3, sub.mission_id, sub.mission.skill.name
                reasons = sorted({r for a in viva.evaluation.get("answers", []) for r in a["grounding"]["reasons"]})
                diagnosis = "Micro-Viva not passed: " + ("; ".join(reasons) or "answers did not show understanding of the code")
                out = {"engine": viva.evaluation.get("engine"), "reply": diagnosis + ". Resubmit to receive a fresh viva.",
                       "guiding_question": "Can you explain each line of your solution aloud without looking anything up?"}
                focus = f"{skill_name} explain how it works complexity"
            else:
                sub = db.get(Submission, payload["submission_id"])
                m = sub.mission
                skill_id, target_tier, mission_id, skill_name = m.skill_id, 3 if m.kind == "applied" else 2, m.id, m.skill.name
                ctx = {"mission_title": m.title, "brief": m.brief, "language": sub.language, "code": sub.code, "message": "",
                       "test_report": sub.test_report.get("visible"), "ast_report": sub.ast_report, "history": []}
                if sub.test_report.get("visible", {}).get("passed") and not sub.tests_passed:
                    ctx["test_report"] = {"status": sub.test_report["hidden"]["status"],
                                          "results": [{"name": "hidden", "passed": False}]}
                out, focus = None, f"{skill_name} {m.title}"
        if out is None:
            out = await mentor.mentor_reply(ctx)
        msg = f"{out['reply']} {out['guiding_question']}".strip()
        with session_scope() as db:
            _say(db, state["profile_id"], msg, {"task": task, "engine": out["engine"]}, mission_id)
        return {"task": task, "skill_id": skill_id, "target_tier": target_tier, "diagnosis": out["reply"][:300],
                "guiding_question": out["guiding_question"], "focus_query": focus, "engine": out["engine"]}

    if task == "nudge":
        det = outputs.get("skill_detective", {})
        nxt = det.get("next_item")
        msg = (f"It has been {det.get('days_inactive', 0)} day(s) since your last activity. "
               + (f"Your next step is small: {nxt['skill']} ({nxt['step']}). " if nxt else "")
               + f"I re-spread your remaining {strat.get('total_hours', 0)} hours over {strat.get('weeks_needed', 0)} week(s). "
               "What is one 25-minute block you can commit to today?")
        with session_scope() as db:
            _say(db, state["profile_id"], msg, {"task": task})
        return {"task": task, "message": msg, "engine": "deterministic-template"}
    raise ValueError(f"ai_mentor: unknown task {task}")


HANDLERS = {
    "skill_detective": skill_detective,
    "career_architect": career_architect,
    "learning_strategist": learning_strategist,
    "resource_scout": resource_scout,
    "skill_validator": skill_validator,
    "ai_mentor": ai_mentor,
}
