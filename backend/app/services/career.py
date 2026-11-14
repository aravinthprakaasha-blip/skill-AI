"""Career Gap Simulator: deterministic, explainable Role Match Score.

score = 100 * sum(weight_i * min(verified_tier_i / required_tier_i, 1)) / sum(weight_i)

over the role's core (non-optional) competency requirements. Only *verified* tiers count:
a self-claimed (Tier 0) skill contributes nothing. Weights follow O*NET-style importance (1-5);
skills carry SFIA 8 skill codes and roles an SFIA level of responsibility.
"""
from sqlalchemy.orm import Session

from ..models import CareerRole, LearnerProfile
from . import skill_dna

FORMULA = "100 × Σ(weight × min(verified_tier / required_tier, 1)) / Σ(weight), core requirements only"


def gap_analysis(db: Session, profile: LearnerProfile, role: CareerRole, overrides: dict[int, int] | None = None) -> dict:
    tiers = skill_dna.tiers(db, profile.id)
    claimed = {ls.skill_id for ls in profile.skills if ls.claimed}
    if overrides:
        tiers = {**tiers, **{int(k): max(0, min(3, int(v))) for k, v in overrides.items()}}
    rows, total_w, total_c = [], 0.0, 0.0
    for req in sorted(role.requirements, key=lambda r: (r.optional, -r.weight, r.skill.name)):
        tier = tiers.get(req.skill_id, 0)
        coverage = min(tier / req.required_tier, 1.0) if req.required_tier else 1.0
        contribution = req.weight * coverage
        if not req.optional:
            total_w += req.weight
            total_c += contribution
        rows.append(
            {
                "skill_id": req.skill_id,
                "slug": req.skill.slug,
                "name": req.skill.name,
                "category": req.skill.category,
                "sfia_code": req.skill.sfia_code,
                "required_tier": req.required_tier,
                "verified_tier": tier,
                "claimed_unverified": tier == 0 and req.skill_id in claimed,
                "weight": req.weight,
                "critical": req.critical,
                "optional": req.optional,
                "coverage": round(coverage, 3),
                "contribution": round(contribution, 3),
                "max_contribution": req.weight,
                "status": "met" if tier >= req.required_tier else ("partial" if tier > 0 else "missing"),
            }
        )
    score = round(100 * total_c / total_w, 1) if total_w else 0.0
    core = [r for r in rows if not r["optional"]]
    return {
        "role": {
            "id": role.id,
            "slug": role.slug,
            "title": role.title,
            "description": role.description,
            "onet_code": role.onet_code,
            "sfia_level": role.sfia_level,
        },
        "match_score": score,
        "formula": FORMULA,
        "weighted_points": round(total_c, 3),
        "max_points": round(total_w, 3),
        "requirements": rows,
        "critical_missing": [r for r in core if r["critical"] and r["status"] != "met"],
        "gaps": [r for r in core if r["status"] != "met"],
        "recommended": [r for r in rows if r["optional"] and r["status"] != "met"],
        "met_count": sum(1 for r in core if r["status"] == "met"),
        "core_count": len(core),
        "simulated": bool(overrides),
    }


def role_scores(db: Session, profile: LearnerProfile) -> list[dict]:
    out = []
    for role in db.query(CareerRole).order_by(CareerRole.title):
        g = gap_analysis(db, profile, role)
        out.append(
            {
                **g["role"],
                "match_score": g["match_score"],
                "critical_missing": len(g["critical_missing"]),
                "gaps": len(g["gaps"]),
            }
        )
    return out
