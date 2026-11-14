"""Prerequisite DAG + adaptive roadmap generation, pivot and remediation."""
import heapq
import math

from sqlalchemy.orm import Session

from ..models import (
    CareerRole,
    LearnerProfile,
    Mission,
    Resource,
    Roadmap,
    RoadmapItem,
    Skill,
    SkillPrerequisite,
)
from . import skill_dna

STEP_FOR_TIER = {1: "concept", 2: "coding", 3: "applied"}
CONCEPT_HOURS = 1.5
PREREQ_TIER = 1  # prerequisites outside the role need conceptual mastery only


class CycleError(ValueError):
    pass


def prereq_map(db: Session) -> dict[int, set[int]]:
    out: dict[int, set[int]] = {}
    for row in db.query(SkillPrerequisite):
        out.setdefault(row.skill_id, set()).add(row.prereq_id)
    return out


def closure(skill_ids: set[int], prereqs: dict[int, set[int]]) -> set[int]:
    seen, stack = set(), list(skill_ids)
    while stack:
        s = stack.pop()
        if s in seen:
            continue
        seen.add(s)
        stack.extend(prereqs.get(s, ()))
    return seen


def topo_order(nodes: set[int], prereqs: dict[int, set[int]], priority: dict[int, float]) -> list[int]:
    """Kahn's algorithm; ties broken by priority (higher first). Raises CycleError on cycles."""
    indeg = {n: len(prereqs.get(n, set()) & nodes) for n in nodes}
    dependents: dict[int, list[int]] = {}
    for n in nodes:
        for p in prereqs.get(n, set()) & nodes:
            dependents.setdefault(p, []).append(n)
    heap = [(-priority.get(n, 0), n) for n in nodes if indeg[n] == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        _, n = heapq.heappop(heap)
        order.append(n)
        for d in dependents.get(n, []):
            indeg[d] -= 1
            if indeg[d] == 0:
                heapq.heappush(heap, (-priority.get(d, 0), d))
    if len(order) != len(nodes):
        raise CycleError("Prerequisite graph contains a cycle")
    return order


def levels(nodes: set[int], prereqs: dict[int, set[int]], order: list[int]) -> dict[int, int]:
    lvl: dict[int, int] = {}
    for n in order:
        ps = prereqs.get(n, set()) & nodes
        lvl[n] = 1 + max((lvl[p] for p in ps), default=-1)
    return lvl


def plan_targets(db: Session, profile: LearnerProfile, role: CareerRole) -> dict:
    """Which skills the learner still needs, and to which tier."""
    tiers = skill_dna.tiers(db, profile.id)
    prereqs = prereq_map(db)
    reqs = {r.skill_id: r for r in role.requirements if not r.optional}
    targets = {sid: r.required_tier for sid, r in reqs.items()}
    for sid in closure(set(reqs), prereqs) - set(reqs):
        targets[sid] = PREREQ_TIER
    needed = {sid: t for sid, t in targets.items() if tiers.get(sid, 0) < t}
    priority = {sid: (reqs[sid].weight + (5 if reqs[sid].critical else 0)) if sid in reqs else 1.0 for sid in targets}
    return {"tiers": tiers, "prereqs": prereqs, "reqs": reqs, "targets": targets, "needed": needed, "priority": priority}


def build_dag(db: Session, profile: LearnerProfile, role: CareerRole) -> dict:
    p = plan_targets(db, profile, role)
    nodes = set(p["targets"])
    order = topo_order(nodes, p["prereqs"], p["priority"])
    lvl = levels(nodes, p["prereqs"], order)
    skills = {s.id: s for s in db.query(Skill).filter(Skill.id.in_(nodes))}
    out_nodes = []
    for i, sid in enumerate(order):
        tier, target = p["tiers"].get(sid, 0), p["targets"][sid]
        blocked = any(p["tiers"].get(q, 0) < 1 for q in p["prereqs"].get(sid, set()) & nodes)
        out_nodes.append(
            {
                "id": sid,
                "slug": skills[sid].slug,
                "name": skills[sid].name,
                "category": skills[sid].category,
                "tier": tier,
                "target_tier": target,
                "level": lvl[sid],
                "order": i,
                "in_role": sid in p["reqs"],
                "critical": sid in p["reqs"] and p["reqs"][sid].critical,
                "status": "met" if tier >= target else ("blocked" if blocked else "ready"),
            }
        )
    edges = [
        {"source": q, "target": sid} for sid in nodes for q in sorted(p["prereqs"].get(sid, set()) & nodes)
    ]
    return {"nodes": out_nodes, "edges": edges, "order": order}


def _schedule(items: list[RoadmapItem], weekly_hours: int, timeline_weeks: int) -> dict:
    hours, weekly = 0.0, max(1, weekly_hours)
    for it in items:
        if it.status != "pending":
            continue
        it.week = int(hours // weekly) + 1
        hours += it.est_hours
    weeks = math.ceil(hours / weekly) if hours else 0
    return {
        "total_hours": round(hours, 1),
        "weeks_needed": weeks,
        "timeline_weeks": timeline_weeks,
        "fits_timeline": weeks <= timeline_weeks,
        "weekly_hours": weekly,
    }


def active_roadmap(db: Session, profile_id: str) -> Roadmap | None:
    return (
        db.query(Roadmap).filter_by(profile_id=profile_id, status="active").order_by(Roadmap.id.desc()).first()
    )


def generate(db: Session, profile: LearnerProfile, role: CareerRole, reason: str = "onboard") -> dict:
    """(Re)build the roadmap from verified tiers. Returns a structured diff.

    Only tasks for genuinely missing tiers are created, so verified skills transfer
    automatically across a pivot. Pending tasks of the previous roadmap are marked
    `carried` when still needed by the new plan, or `archived` when no longer relevant.
    """
    p = plan_targets(db, profile, role)
    needed = p["needed"]
    order = [s for s in topo_order(set(p["targets"]), p["prereqs"], p["priority"]) if s in needed]
    skills = {s.id: s for s in db.query(Skill).filter(Skill.id.in_(set(p["targets"]) | set(p["tiers"])))}

    old = active_roadmap(db, profile.id)
    archived, carried = [], []
    if old:
        for it in old.items:
            if it.status == "pending":
                keep = it.skill_id in needed and it.target_tier <= needed[it.skill_id]
                it.status = "carried" if keep else "archived"
                (carried if keep else archived).append({"skill": it.skill.name, "step": it.step})
        old.status = "archived"

    rm = Roadmap(profile_id=profile.id, role_id=role.id, status="active")
    db.add(rm)
    idx = 0
    for sid in order:
        for t in range(p["tiers"].get(sid, 0) + 1, needed[sid] + 1):
            step = STEP_FOR_TIER[t]
            mission = None
            if step != "concept":
                mission = db.query(Mission).filter_by(skill_id=sid, kind=step).order_by(Mission.id).first()
            in_role = sid in p["reqs"]
            why = (
                f"{role.title} requires Tier {needed[sid]} ({skill_dna.TIER_NAMES[needed[sid]]})"
                if in_role
                else "Prerequisite for a required skill"
            )
            if in_role and p["reqs"][sid].critical:
                why += " - critical competency"
            rm.items.append(
                RoadmapItem(
                    skill_id=sid,
                    step=step,
                    target_tier=t,
                    order_index=idx,
                    est_hours=CONCEPT_HOURS if step == "concept" else (mission.est_hours if mission else 3.0),
                    mission_id=mission.id if mission else None,
                    rationale=why,
                )
            )
            idx += 1
    db.flush()
    rm.summary = _schedule(rm.items, profile.weekly_hours, profile.timeline_weeks)
    old_role_skills = {r.skill_id for r in old.role.requirements} if old else set()
    transferable = [
        {"skill": skills[sid].name, "tier": p["tiers"][sid]}
        for sid in p["reqs"]
        if p["tiers"].get(sid, 0) >= 1 and sid in skills
    ]
    rm.summary = {
        **rm.summary,
        "reason": reason,
        "transferable": transferable,
        "newly_missing": [skills[s].name for s in order if s not in old_role_skills] if old else [],
        "archived": archived,
        "carried": carried,
    }
    db.flush()
    return {
        "roadmap_id": rm.id,
        "role": role.title,
        "items_created": len(rm.items),
        "skills_in_order": [skills[s].slug for s in order],
        **rm.summary,
    }


def refresh_progress(db: Session, profile: LearnerProfile) -> list[int]:
    """Mark roadmap items done when verified evidence reaches their target tier."""
    rm = active_roadmap(db, profile.id)
    if not rm:
        return []
    tiers = skill_dna.tiers(db, profile.id)
    done = []
    for it in rm.items:
        if it.status == "pending" and it.step != "remediation" and tiers.get(it.skill_id, 0) >= it.target_tier:
            it.status = "done"
            done.append(it.id)
        if it.status == "pending" and it.step == "remediation" and tiers.get(it.skill_id, 0) >= it.target_tier:
            it.status = "done"
    rm.summary = {**rm.summary, **_schedule(rm.items, profile.weekly_hours, profile.timeline_weeks)}
    return done


def add_remediation(db: Session, profile: LearnerProfile, skill_id: int, target_tier: int, reason: str, resource_ids: list[int]) -> dict | None:
    """Insert a targeted review task ahead of the step the learner just failed."""
    rm = active_roadmap(db, profile.id)
    if not rm:
        return None
    for it in rm.items:
        if it.step == "remediation" and it.skill_id == skill_id and it.status == "pending":
            it.resource_ids = sorted(set(it.resource_ids) | set(resource_ids))
            it.rationale = reason[:400]
            return {"item_id": it.id, "updated": True}
    anchor = next(
        (it for it in rm.items if it.skill_id == skill_id and it.status == "pending" and it.target_tier == target_tier),
        None,
    )
    pos = anchor.order_index if anchor else 0
    for it in rm.items:
        if it.order_index >= pos:
            it.order_index += 1
    item = RoadmapItem(
        skill_id=skill_id,
        step="remediation",
        target_tier=target_tier,
        order_index=pos,
        est_hours=1.0,
        rationale=reason[:400],
        resource_ids=resource_ids,
    )
    rm.items.append(item)
    db.flush()
    db.refresh(rm)
    rm.summary = {**rm.summary, **_schedule(rm.items, profile.weekly_hours, profile.timeline_weeks)}
    return {"item_id": item.id, "updated": False}


def reschedule(db: Session, profile: LearnerProfile) -> dict | None:
    rm = active_roadmap(db, profile.id)
    if not rm:
        return None
    rm.summary = {**rm.summary, **_schedule(rm.items, profile.weekly_hours, profile.timeline_weeks)}
    nxt = next((it for it in rm.items if it.status == "pending"), None)
    return {**rm.summary, "next_item_id": nxt.id if nxt else None}


def serialize(db: Session, rm: Roadmap | None) -> dict | None:
    if not rm:
        return None
    res_ids = {rid for it in rm.items for rid in it.resource_ids}
    res = {r.id: r for r in db.query(Resource).filter(Resource.id.in_(res_ids))} if res_ids else {}
    items = []
    for it in rm.items:
        items.append(
            {
                "id": it.id,
                "skill_id": it.skill_id,
                "skill": it.skill.name,
                "skill_slug": it.skill.slug,
                "step": it.step,
                "target_tier": it.target_tier,
                "status": it.status,
                "week": it.week,
                "est_hours": it.est_hours,
                "rationale": it.rationale,
                "mission": {"id": it.mission.id, "title": it.mission.title, "kind": it.mission.kind}
                if it.mission
                else None,
                "resources": [
                    {"id": r.id, "title": r.title, "url": r.url, "source": r.source, "kind": r.kind}
                    for r in (res.get(i) for i in it.resource_ids)
                    if r
                ],
            }
        )
    pending = [i for i in items if i["status"] == "pending"]
    done = [i for i in items if i["status"] == "done"]
    return {
        "id": rm.id,
        "role": {"id": rm.role.id, "title": rm.role.title, "slug": rm.role.slug},
        "status": rm.status,
        "created_at": rm.created_at.isoformat(),
        "summary": rm.summary,
        "items": items,
        "progress": {"done": len(done), "pending": len(pending), "total": len(done) + len(pending)},
    }
