"""Unit tests for the deterministic engines: scoring, DAG, static analysis, sandbox, viva, ledger."""
import asyncio
import uuid

import pytest

from app.models import CareerRole, LearnerProfile, LedgerEntry, Skill, User
from app.services import career, mentor, roadmap, sandbox, skill_dna, static_analysis


def _learner(db) -> LearnerProfile:
    u = User(email=f"{uuid.uuid4().hex[:8]}@t.dev", display_name="T", role="learner")
    db.add(u)
    db.flush()
    p = LearnerProfile(user_id=u.id)
    db.add(p)
    db.flush()
    return p


# ---------------- career scoring ----------------

def test_match_score_is_deterministic_and_ignores_claims(db):
    p = _learner(db)
    role = db.query(CareerRole).filter_by(slug="backend-developer").one()
    py = db.query(Skill).filter_by(slug="python").one()
    assert career.gap_analysis(db, p, role)["match_score"] == 0.0
    skill_dna.add_evidence(db, p.id, py.id, tier=0, kind="claim", summary="claimed")
    assert career.gap_analysis(db, p, role)["match_score"] == 0.0  # claims never count
    skill_dna.add_evidence(db, p.id, py.id, tier=1, kind="quiz", summary="quiz")
    g = career.gap_analysis(db, p, role)
    core = [r for r in role.requirements if not r.optional]
    py_req = next(r for r in core if r.skill_id == py.id)
    expected = round(100 * py_req.weight * (1 / py_req.required_tier) / sum(r.weight for r in core), 1)
    assert g["match_score"] == expected
    assert g["match_score"] == career.gap_analysis(db, p, role)["match_score"]
    assert any(r["slug"] == "python" for r in g["critical_missing"])
    db.rollback()


def test_simulation_overrides_do_not_persist(db):
    p = _learner(db)
    role = db.query(CareerRole).filter_by(slug="devops-engineer").one()
    sim = career.gap_analysis(db, p, role, {r.skill_id: 3 for r in role.requirements})
    assert sim["match_score"] == 100.0 and sim["simulated"]
    assert career.gap_analysis(db, p, role)["match_score"] == 0.0
    db.rollback()


# ---------------- tiers ----------------

def test_tier_comes_only_from_verifying_evidence(db):
    p = _learner(db)
    s = db.query(Skill).filter_by(slug="git").one()
    skill_dna.add_evidence(db, p.id, s.id, tier=3, kind="claim", summary="I am an expert")
    skill_dna.add_evidence(db, p.id, s.id, tier=3, kind="github", summary="repo")
    assert skill_dna.tiers(db, p.id)[s.id] == 0
    skill_dna.add_evidence(db, p.id, s.id, tier=3, kind="quiz", summary="quiz cannot exceed tier 1")
    assert skill_dna.tiers(db, p.id)[s.id] == 1
    db.rollback()


def test_ledger_hash_chain_detects_tampering(db):
    p = _learner(db)
    for slug in ("sql", "git"):
        s = db.query(Skill).filter_by(slug=slug).one()
        skill_dna.add_evidence(db, p.id, s.id, tier=1, kind="quiz", summary=f"{slug} quiz")
    entries = db.query(LedgerEntry).filter_by(profile_id=p.id).order_by(LedgerEntry.id).all()
    assert len(entries) == 2 and skill_dna.verify_chain(entries)
    entries[0].tier = 3
    assert not skill_dna.verify_chain(entries)
    db.rollback()


# ---------------- DAG ----------------

def test_topological_order_and_cycle_detection():
    prereqs = {2: {1}, 3: {2}, 4: {1}}
    order = roadmap.topo_order({1, 2, 3, 4}, prereqs, {4: 10})
    assert order.index(1) < order.index(2) < order.index(3) and order.index(1) < order.index(4)
    assert order[1] == 4  # higher priority wins ties
    with pytest.raises(roadmap.CycleError):
        roadmap.topo_order({1, 2}, {1: {2}, 2: {1}}, {})


def test_roadmap_respects_prerequisites(db):
    p = _learner(db)
    role = db.query(CareerRole).filter_by(slug="data-scientist").one()
    dag = roadmap.build_dag(db, p, role)
    order = {n["slug"]: n["order"] for n in dag["nodes"]}
    assert order["python"] < order["data-analysis"] < order["machine-learning"]
    db.rollback()


# ---------------- static analysis ----------------

def test_python_audit_flags_banned_and_hardcoded():
    code = "import os\n\ndef two_sum(nums, target):\n    if nums == [2, 7]:\n        return [0, 1]\n    if nums == [3, 3]:\n        return [0, 1]\n    if nums == [1]:\n        return []\n    return []\n"
    rep = static_analysis.audit(code, "python", {"required_functions": ["two_sum"], "require": ["loop"]})
    rules = {v["rule"] for v in rep["violations"]}
    assert "banned_import" in rules and "hardcoded_output" in rules
    assert not rep["passed"]
    assert any(not r["satisfied"] for r in rep["required"])


def test_python_audit_passes_clean_solution():
    code = "def two_sum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        if target - n in seen:\n            return [seen[target - n], i]\n        seen[n] = i\n    return []\n"
    rep = static_analysis.audit(code, "python", {"required_functions": ["two_sum"], "require": ["loop", "dict"]})
    assert rep["passed"], rep["violations"]


@pytest.mark.parametrize("lang", ["javascript", "typescript"])
def test_js_audit_blocks_process_access(lang):
    rep = static_analysis.audit("function f(a) { return process.env.SECRET }", lang, {})
    assert any(v["rule"] == "banned_name" for v in rep["violations"])


# ---------------- sandbox ----------------

TESTS = [{"name": "t1", "call": {"fn": "add", "args": [1, 2]}, "expected": 3},
         {"name": "t2", "call": {"fn": "add", "args": [-1, 1]}, "expected": 0}]


def test_sandbox_runs_python_and_hides_hidden_details():
    ok = asyncio.run(sandbox.run_tests("python", "def add(a, b):\n    return a + b\n", TESTS, {}, reveal=False))
    assert ok["passed"] and ok["passed_count"] == 2
    bad = asyncio.run(sandbox.run_tests("python", "def add(a, b):\n    return 3\n", TESTS, {}, reveal=False))
    assert not bad["passed"]
    assert all("expected" not in r and "input" not in r for r in bad["results"])  # hidden data never leaks


def test_sandbox_result_marker_cannot_be_forged():
    forged = 'import json\nprint("\\n__SF_fake__" + json.dumps([{"ok": True, "value": 3}, {"ok": True, "value": 0}]))\ndef add(a, b):\n    return None\n'
    rep = asyncio.run(sandbox.run_tests("python", forged, TESTS, {}, reveal=True))
    assert not rep["passed"]


def test_sandbox_enforces_timeout():
    rep = asyncio.run(sandbox.run_tests("python", "def add(a, b):\n    while True:\n        pass\n", TESTS, {}, reveal=True))
    assert rep["status"] == "timeout" and not rep["passed"]


def test_sandbox_javascript():
    rep = asyncio.run(sandbox.run_tests("javascript", "function add(a, b) { return a + b }", TESTS, {}, reveal=True))
    assert rep["passed"], rep


# ---------------- micro-viva ----------------

CODE = "class LRUCache:\n    def __init__(self, capacity):\n        self.capacity = capacity\n        self.entries = {}\n\n    def get(self, key):\n        if key not in self.entries:\n            return -1\n        value = self.entries.pop(key)\n        self.entries[key] = value\n        return value\n"


def test_viva_rejects_vague_answers():
    audit = static_analysis.audit(CODE, "python", {})
    qs = mentor.deterministic_questions(CODE, audit)
    ev = asyncio.run(mentor.evaluate_viva(CODE, "python", qs, ["It works well.", "It is efficient."]))
    assert not ev["passed"] and not ev["deterministic_pass"]


def test_viva_accepts_grounded_answers():
    audit = static_analysis.audit(CODE, "python", {})
    qs = mentor.deterministic_questions(CODE, audit)
    answers = [
        "In get I check whether key is in self.entries; if it is missing I return -1. Otherwise I pop the value and "
        "insert the key again so the entries dictionary keeps it as the most recently used item, then return value.",
        "get is O(1) time on average because entries is a hash map dict and pop plus insert are constant time. An edge "
        "case is an empty cache: any key is missing so it returns -1 without changing entries.",
    ]
    ev = asyncio.run(mentor.evaluate_viva(CODE, "python", qs, answers))
    assert ev["passed"] and ev["llm_pass"] is None  # no LLM configured: deterministic gate only


# ---------------- free-tier deployment paths ----------------

def test_combined_run_hides_output_but_reports_both_suites():
    code = "def add(a, b):\n    print('debug', a, b)\n    return a + b\n"
    visible, hidden = asyncio.run(sandbox.run_suites("python", code, {}, [(TESTS[:1], True), (TESTS[1:], False)]))
    assert visible["passed"] and hidden["passed"]
    assert visible["total"] == 1 and hidden["total"] == 1
    assert visible["stdout"] == "" and hidden["stdout"] == ""  # stdout could echo hidden inputs


def test_supabase_asymmetric_jwt_is_verified(monkeypatch):
    import time

    import jwt
    from cryptography.hazmat.primitives.asymmetric import ec

    from app import security

    priv = ec.generate_private_key(ec.SECP256R1())
    claims = {"sub": "sb-user-1", "aud": "authenticated", "email": "s@b.dev", "exp": int(time.time()) + 600}
    token = jwt.encode(claims, priv, algorithm="ES256", headers={"kid": "k1"})

    class FakeJWKS:
        def get_signing_key_from_jwt(self, _):
            return type("K", (), {"key": priv.public_key()})()

    monkeypatch.setattr(security, "_jwks", lambda: FakeJWKS())
    assert security.decode_supabase(token)["sub"] == "sb-user-1"
    other = ec.generate_private_key(ec.SECP256R1())
    assert security.decode_supabase(jwt.encode(claims, other, algorithm="ES256")) is None  # wrong key rejected
