"""Skill DNA: tiers are derived only from recorded assessment evidence.

Tier 0  Unverified  - self-claim / GitHub signal
Tier 1  Conceptual  - passed verified quiz
Tier 2  Coding      - passed hidden automated tests + static audit
Tier 3  Applied     - applied mission: hidden tests + AST audit + Micro-Viva
"""
import hashlib
import json
from datetime import date

from sqlalchemy.orm import Session

from ..models import (
    LearnerProfile,
    LearnerSkill,
    LedgerEntry,
    ProgressRecord,
    Skill,
    SkillEvidence,
    utcnow,
)

TIER_NAMES = {0: "Unverified", 1: "Conceptual", 2: "Coding", 3: "Applied"}
VERIFYING_KINDS = {"quiz": 1, "tests": 2, "viva": 3}  # evidence kind -> max tier it can grant


def get_or_create(db: Session, profile_id: str, skill_id: int) -> LearnerSkill:
    ls = db.query(LearnerSkill).filter_by(profile_id=profile_id, skill_id=skill_id).first()
    if not ls:
        ls = LearnerSkill(profile_id=profile_id, skill_id=skill_id, tier=0)
        db.add(ls)
        db.flush()
    return ls


def recompute_tier(ls: LearnerSkill) -> int:
    tier = 0
    for ev in ls.evidence:
        cap = VERIFYING_KINDS.get(ev.kind)
        if cap is not None:
            tier = max(tier, min(ev.tier, cap))
    ls.tier = tier
    return tier


def add_evidence(
    db: Session,
    profile_id: str,
    skill_id: int,
    *,
    tier: int,
    kind: str,
    summary: str,
    data: dict | None = None,
    ref_type: str = "",
    ref_id: int | None = None,
    public_evidence: dict | None = None,
) -> dict:
    """Record evidence, recompute the tier from all evidence, and append to the public ledger."""
    ls = get_or_create(db, profile_id, skill_id)
    before = ls.tier
    if kind == "claim":
        ls.claimed = True
    ls.evidence.append(
        SkillEvidence(tier=tier, kind=kind, summary=summary, data=data or {}, ref_type=ref_type, ref_id=ref_id)
    )
    db.flush()
    after = recompute_tier(ls)
    if kind in VERIFYING_KINDS:
        append_ledger(db, profile_id, skill_id, min(tier, VERIFYING_KINDS[kind]), kind, summary, public_evidence or {})
    db.flush()
    return {"skill_id": skill_id, "tier_before": before, "tier_after": after, "changed": after != before}


def _hash(prev: str, payload: dict) -> str:
    return hashlib.sha256((prev + json.dumps(payload, sort_keys=True, default=str)).encode()).hexdigest()


def _ledger_payload(e: LedgerEntry) -> dict:
    return {
        "profile": e.profile_id,
        "skill": e.skill_id,
        "tier": e.tier,
        "kind": e.kind,
        "summary": e.summary,
        "evidence": e.evidence,
        "at": e.created_at.isoformat(),
    }


def append_ledger(db: Session, profile_id: str, skill_id: int, tier: int, kind: str, summary: str, evidence: dict):
    last = (
        db.query(LedgerEntry).filter_by(profile_id=profile_id).order_by(LedgerEntry.id.desc()).first()
    )
    entry = LedgerEntry(
        profile_id=profile_id,
        skill_id=skill_id,
        tier=tier,
        kind=kind,
        summary=summary,
        evidence=evidence,
        prev_hash=last.entry_hash if last else "",
        created_at=utcnow().replace(microsecond=0),
        entry_hash="",
    )
    entry.entry_hash = _hash(entry.prev_hash, _ledger_payload(entry))
    db.add(entry)
    return entry


def verify_chain(entries: list[LedgerEntry]) -> bool:
    prev = ""
    for e in entries:
        if e.prev_hash != prev or e.entry_hash != _hash(prev, _ledger_payload(e)):
            return False
        prev = e.entry_hash
    return True


def tiers(db: Session, profile_id: str) -> dict[int, int]:
    return {ls.skill_id: ls.tier for ls in db.query(LearnerSkill).filter_by(profile_id=profile_id)}


def matrix(db: Session, profile: LearnerProfile) -> list[dict]:
    owned = {ls.skill_id: ls for ls in profile.skills}
    required = {}
    if profile.target_role:
        required = {r.skill_id: r for r in profile.target_role.requirements}
    out = []
    for s in db.query(Skill).order_by(Skill.category, Skill.name):
        ls = owned.get(s.id)
        req = required.get(s.id)
        out.append(
            {
                "skill_id": s.id,
                "slug": s.slug,
                "name": s.name,
                "category": s.category,
                "description": s.description,
                "sfia_code": s.sfia_code,
                "tier": ls.tier if ls else 0,
                "tier_name": TIER_NAMES[ls.tier if ls else 0],
                "claimed": bool(ls and ls.claimed),
                "tracked": ls is not None,
                "required_tier": req.required_tier if req else None,
                "critical": bool(req and req.critical),
                "evidence": [
                    {
                        "id": e.id,
                        "tier": e.tier,
                        "kind": e.kind,
                        "summary": e.summary,
                        "data": e.data,
                        "verifying": e.kind in VERIFYING_KINDS,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in (ls.evidence if ls else [])
                ],
            }
        )
    return out


def record_progress(db: Session, profile_id: str, kind: str, value: dict | None = None, day: date | None = None):
    db.add(ProgressRecord(profile_id=profile_id, day=day or utcnow().date(), kind=kind, value=value or {}))
    prof = db.get(LearnerProfile, profile_id)
    if prof and day is None:
        prof.last_active_at = utcnow()
