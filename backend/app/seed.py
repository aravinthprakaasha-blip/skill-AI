"""Seeding: catalog (idempotent) and demo learner journeys.

Demo journeys are NOT inserted as pre-baked results. Each one is driven through the real
pipeline - agent graph, quiz grader, sandboxed test execution, AST audit and Micro-Viva - so
every tier and score you see for a demo learner was actually earned by real evidence.

Run manually:  python -m app.seed [--demo]
"""
import asyncio
import logging
import sys

from .config import get_settings
from .db import init_db, session_scope
from .models import (
    CareerRole,
    CompetencyRequirement,
    LearnerProfile,
    Mission,
    Project,
    QuizQuestion,
    Resource,
    Skill,
    SkillPrerequisite,
    Submission,
    User,
    VivaSession,
)
from .security import hash_password
from . import seed_data as D

log = logging.getLogger("skillforge.seed")

# Local demo accounts (development only - documented in README / .env.example).
DEMO_PASSWORD = "skillforge-demo"
DEMO_USERS = [
    ("maya@demo.skillforge.dev", "Maya Chen", "learner"),
    ("leo@demo.skillforge.dev", "Leo Okafor", "learner"),
    ("recruiter@demo.skillforge.dev", "Riley Recruiter", "recruiter"),
    ("admin@demo.skillforge.dev", "Ada Admin", "admin"),
]


def seed_catalog() -> None:
    with session_scope() as db:
        skills = {s.slug: s for s in db.query(Skill)}
        for slug, name, cat, sfia, desc, aliases in D.SKILLS:
            s = skills.get(slug) or Skill(slug=slug)
            s.name, s.category, s.sfia_code, s.description, s.aliases = name, cat, sfia, desc, aliases
            db.add(s)
            skills[slug] = s
        db.flush()
        existing = {(p.skill_id, p.prereq_id) for p in db.query(SkillPrerequisite)}
        for a, b in D.PREREQUISITES:
            if (skills[a].id, skills[b].id) not in existing:
                db.add(SkillPrerequisite(skill_id=skills[a].id, prereq_id=skills[b].id))
        for r in D.ROLES:
            role = db.query(CareerRole).filter_by(slug=r["slug"]).first() or CareerRole(slug=r["slug"])
            role.title, role.description, role.onet_code, role.sfia_level = r["title"], r["description"], r["onet_code"], r["sfia_level"]
            db.add(role)
            db.flush()
            have = {q.skill_id: q for q in role.requirements}
            for slug, tier, weight, critical, optional in r["requirements"]:
                q = have.get(skills[slug].id) or CompetencyRequirement(role_id=role.id, skill_id=skills[slug].id)
                q.required_tier, q.weight, q.critical, q.optional = tier, float(weight), critical, optional
                db.add(q)
        for slug, qs in D.QUIZZES.items():
            if not db.query(QuizQuestion).filter_by(skill_id=skills[slug].id).count():
                for prompt, opts, ans, expl in qs:
                    db.add(QuizQuestion(skill_id=skills[slug].id, prompt=prompt, options=opts, answer_index=ans, explanation=expl))
        for m in D.MISSIONS:
            row = db.query(Mission).filter_by(slug=m["slug"]).first() or Mission(slug=m["slug"])
            row.skill_id = skills[m["skill"]].id
            row.title, row.kind, row.difficulty, row.brief, row.docs = m["title"], m["kind"], m["difficulty"], m["brief"], m["docs"]
            row.languages, row.visible_tests, row.hidden_tests = m["languages"], m["visible"], m["hidden"]
            row.ast_rules, row.est_hours = m["ast_rules"], m["est_hours"]
            db.add(row)
        urls = {r.url for r in db.query(Resource)}
        for slug, title, url, source, kind, summary in D.RESOURCES:
            if url not in urls:
                db.add(Resource(skill_id=skills[slug].id, title=title, url=url, source=source, kind=kind, summary=summary))


async def index_resources() -> int:
    from .services import resources

    with session_scope() as db:
        return await resources.index_all(db)


# ---------------- demo journeys (real pipeline) ----------------

SOLUTIONS = {
    "py-word-frequency": (
        "python",
        "PUNCT = \".,!?;:\"\n\n\ndef word_frequency(text):\n    \"\"\"Count lowercase words after stripping edge punctuation.\"\"\"\n"
        "    counts = {}\n    for token in text.split():\n        word = token.strip(PUNCT).lower()\n        if word:\n"
        "            counts[word] = counts.get(word, 0) + 1\n    return counts\n",
    ),
    "ds-valid-brackets": (
        "python",
        "PAIRS = {')': '(', ']': '[', '}': '{'}\n\n\ndef is_balanced(s):\n    \"\"\"Stack of open brackets; each closer must match the top.\"\"\"\n"
        "    stack = []\n    for ch in s:\n        if ch in '([{':\n            stack.append(ch)\n        elif ch in PAIRS:\n"
        "            if not stack or stack.pop() != PAIRS[ch]:\n                return False\n    return not stack\n",
    ),
    "ds-lru-cache": (
        "python",
        "from collections import OrderedDict\n\n\nclass LRUCache:\n    \"\"\"OrderedDict keeps keys in recency order: oldest first.\"\"\"\n\n"
        "    def __init__(self, capacity):\n        self.capacity = capacity\n        self.entries = OrderedDict()\n\n"
        "    def get(self, key):\n        if key not in self.entries:\n            return -1\n        self.entries.move_to_end(key)\n"
        "        return self.entries[key]\n\n    def put(self, key, value):\n        self.entries[key] = value\n"
        "        self.entries.move_to_end(key)\n        if len(self.entries) > self.capacity:\n"
        "            self.entries.popitem(last=False)\n",
    ),
    "js-group-by": (
        "javascript",
        "function groupBy(items, key) {\n  const groups = {};\n  for (const item of items) {\n    const bucket = String(item[key]);\n"
        "    if (!groups[bucket]) groups[bucket] = [];\n    groups[bucket].push(item);\n  }\n  return groups;\n}\n",
    ),
}
VIVA_ANSWERS = {
    "ds-lru-cache": [
        "In my LRUCache class, get first checks whether the key is in self.entries, which is an OrderedDict. If it is missing "
        "I return -1. Otherwise I call move_to_end so the key becomes the most recently used and return its value. put stores "
        "the value, calls move_to_end, and if len(self.entries) exceeds self.capacity it calls popitem(last=False) to evict "
        "the least recently used key at the front of the ordered dictionary.",
        "Both get and put are O(1) time because the OrderedDict lookup is a hash map and move_to_end and popitem are constant "
        "time; space is O(capacity). An edge case is capacity 1: putting a second key evicts the first, so get on the old key "
        "returns -1. A get on an empty cache also returns -1 without changing anything.",
    ],
}


async def _wait_for(sub_id: int) -> str:
    from .jobs import dispatch

    await dispatch(_profile_of(sub_id), "SUBMIT_CODE", {"submission_id": sub_id})
    with session_scope() as db:
        return db.get(Submission, sub_id).status


def _profile_of(sub_id: int) -> str:
    with session_scope() as db:
        return db.get(Submission, sub_id).profile_id


async def _quiz(profile_id: str, slug: str, perfect: bool = True):
    from .jobs import dispatch
    from .services import assessments

    with session_scope() as db:
        skill = db.query(Skill).filter_by(slug=slug).one()
        qs = db.query(QuizQuestion).filter_by(skill_id=skill.id).order_by(QuizQuestion.id).all()
        answers = {q.id: (q.answer_index if perfect or i % 2 == 0 else (q.answer_index + 1) % len(q.options)) for i, q in enumerate(qs)}
        a = assessments.grade(db, profile_id, skill, answers)
        aid, passed = a.id, a.passed
    await dispatch(profile_id, "ASSESSMENT_PASSED" if passed else "ASSESSMENT_FAILED", {"kind": "quiz", "assessment_id": aid})


async def _submit(profile_id: str, slug: str, code: str | None = None, language: str | None = None) -> int:
    lang, sol = SOLUTIONS.get(slug, (language, code))
    with session_scope() as db:
        m = db.query(Mission).filter_by(slug=slug).one()
        n = db.query(Submission).filter_by(profile_id=profile_id, mission_id=m.id).count()
        sub = Submission(profile_id=profile_id, mission_id=m.id, language=language or lang, code=code or sol, attempt_no=n + 1)
        db.add(sub)
        db.flush()
        sid = sub.id
    await _wait_for(sid)
    return sid


async def _viva(profile_id: str, sub_id: int, slug: str):
    from .jobs import dispatch
    from .services import mentor

    with session_scope() as db:
        viva = db.query(VivaSession).filter_by(submission_id=sub_id).first()
        if not viva:
            return
        sub = viva.submission
        ev = await mentor.evaluate_viva(sub.code, sub.language, viva.questions, VIVA_ANSWERS[slug])
        viva.answers, viva.evaluation = VIVA_ANSWERS[slug], {**viva.evaluation, **ev}
        viva.status = "passed" if ev["passed"] else "failed"
        vid, passed = viva.id, ev["passed"]
    await dispatch(profile_id, "ASSESSMENT_PASSED" if passed else "ASSESSMENT_FAILED", {"kind": "viva", "viva_id": vid})


async def _wait_for_executor(timeout_s: int = 120) -> bool:
    """Demo journeys execute real code, so wait until Judge0 answers (when configured)."""
    settings = get_settings()
    if not settings.judge0_url:
        return True
    import httpx

    headers = {"X-Auth-Token": settings.judge0_api_key} if settings.judge0_api_key else {}
    for _ in range(timeout_s // 3):
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                if (await c.get(f"{settings.judge0_url.rstrip('/')}/languages", headers=headers)).status_code == 200:
                    return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(3)
    return False


async def seed_demo() -> bool:
    from .jobs import dispatch

    with session_scope() as db:
        if db.query(User).filter_by(email=DEMO_USERS[0][0]).first():
            return False
    if not await _wait_for_executor():
        log.warning("Execution engine not reachable; skipping demo journeys (they require real code execution).")
        return False
    with session_scope() as db:
        ids = {}
        for email, name, role in DEMO_USERS:
            u = User(email=email, display_name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
            db.add(u)
            db.flush()
            if role == "learner":
                db.add(LearnerProfile(user_id=u.id))
            ids[email] = u.id
        db.flush()
        roles = {r.slug: r.id for r in db.query(CareerRole)}
        maya = db.query(LearnerProfile).filter_by(user_id=ids["maya@demo.skillforge.dev"]).one()
        maya.headline, maya.education = "Aspiring backend engineer", "BSc Computer Science (final year)"
        maya.target_role_id, maya.timeline_weeks, maya.weekly_hours = roles["backend-developer"], 12, 10
        maya.github_repos = ["https://github.com/example/inventory-api"]
        maya.projects.append(Project(name="Campus Inventory API", description="REST API for lab equipment tracking", url="https://github.com/example/inventory-api"))
        leo = db.query(LearnerProfile).filter_by(user_id=ids["leo@demo.skillforge.dev"]).one()
        leo.headline, leo.education = "Self-taught web developer", "Diploma in Multimedia Design"
        leo.target_role_id, leo.timeline_weeks, leo.weekly_hours = roles["frontend-developer"], 16, 6
        maya_id, leo_id = maya.id, leo.id
        maya.onboarded = leo.onboarded = True

    log.info("Running demo journeys through the agent pipeline...")
    # Maya: backend journey with Tier 1, Tier 2 and a Tier 3 applied project (with viva)
    await dispatch(maya_id, "ONBOARD", {"claimed_skills": ["Python", "SQL", "Git", "Docker", "React"]})
    for slug in ("python", "data-structures", "sql", "git"):
        await _quiz(maya_id, slug)
    await _quiz(maya_id, "algorithms", perfect=False)  # genuine failed attempt -> remediation
    await _submit(maya_id, "py-word-frequency")
    # A genuinely wrong first attempt at brackets, then a correct one
    await _submit(maya_id, "ds-valid-brackets",
                  code="def is_balanced(s):\n    return s.count('(') == s.count(')')\n", language="python")
    await _submit(maya_id, "ds-valid-brackets")
    lru = await _submit(maya_id, "ds-lru-cache")
    await _viva(maya_id, lru, "ds-lru-cache")

    # Leo: frontend journey, then an autonomous career pivot to full-stack
    await dispatch(leo_id, "ONBOARD", {"claimed_skills": ["JavaScript", "HTML", "CSS", "React", "Figma"]})
    for slug in ("javascript", "html-css", "react"):
        await _quiz(leo_id, slug)
    await _submit(leo_id, "js-group-by")
    await dispatch(leo_id, "PIVOT_GOAL", {"role_slug": "fullstack-developer"})
    log.info("Demo journeys complete.")
    return True


async def seed_all(demo: bool) -> None:
    init_db()
    seed_catalog()
    await index_resources()
    if demo:
        await seed_demo()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_all("--demo" in sys.argv or get_settings().seed_demo_data))
    print("Seed complete.")
