"""End-to-end API journey: register -> onboard -> quiz -> mission -> viva -> pivot -> public ledger."""
import time
import uuid

PY_SOLUTION = (
    "PUNCT = '.,!?;:'\n\n\ndef word_frequency(text):\n    counts = {}\n    for token in text.split():\n"
    "        word = token.strip(PUNCT).lower()\n        if word:\n            counts[word] = counts.get(word, 0) + 1\n    return counts\n"
)
LRU = (
    "from collections import OrderedDict\n\n\nclass LRUCache:\n    def __init__(self, capacity):\n        self.capacity = capacity\n"
    "        self.entries = OrderedDict()\n\n    def get(self, key):\n        if key not in self.entries:\n            return -1\n"
    "        self.entries.move_to_end(key)\n        return self.entries[key]\n\n    def put(self, key, value):\n"
    "        self.entries[key] = value\n        self.entries.move_to_end(key)\n        if len(self.entries) > self.capacity:\n"
    "            self.entries.popitem(last=False)\n"
)


def _wait_run(client, h, run_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/runs/{run_id}", headers=h).json()
        if r["status"] in ("completed", "failed"):
            return r
        time.sleep(0.3)
    raise AssertionError("run did not finish")


def _mission(client, h, slug):
    return next(m for m in client.get("/api/missions", headers=h).json() if m["slug"] == slug)


def _submit(client, h, mission_id, code, lang="python"):
    time.sleep(4.1)  # respect the submit rate limit
    r = client.post(f"/api/missions/{mission_id}/submit", headers=h, json={"language": lang, "code": code})
    assert r.status_code == 200, r.text
    run = _wait_run(client, h, r.json()["run_id"])
    return run, client.get(f"/api/submissions/{r.json()['submission_id']}", headers=h).json()


def test_full_learner_journey(client, db):
    email = f"{uuid.uuid4().hex[:8]}@example.dev"
    r = client.post("/api/auth/register", json={"email": email, "password": "password123", "display_name": "Journey"})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.get("/api/skills", headers={"Authorization": "Bearer nope"}).status_code == 401

    # onboarding -> ONBOARD workflow
    assert client.put("/api/profile", headers=h, json={"target_role_slug": "backend-developer", "weekly_hours": 10}).status_code == 200
    run = _wait_run(client, h, client.post("/api/profile/onboard", headers=h, json={"claimed_skills": ["Python", "Kotlin"]}).json()["run_id"])
    assert run["status"] == "completed"
    assert [s["agent"] for s in run["steps"]] == ["skill_detective", "career_architect", "learning_strategist", "resource_scout", "ai_mentor"]
    assert run["steps"][0]["output"]["unrecognised_claims"] == ["Kotlin"]
    roadmap = client.get("/api/roadmap", headers=h).json()
    assert roadmap["items"] and any(i["resources"] for i in roadmap["items"])

    skills = {s["slug"]: s for s in client.get("/api/skills", headers=h).json()["skills"]}
    assert skills["python"]["tier"] == 0 and skills["python"]["claimed"]

    # quiz: client never sees answers; grading is server-side
    quiz = client.get(f"/api/skills/{skills['python']['skill_id']}/quiz", headers=h).json()
    assert all("answer_index" not in q for q in quiz["questions"])
    from app.models import QuizQuestion

    answers = {q.id: q.answer_index for q in db.query(QuizQuestion).filter_by(skill_id=skills["python"]["skill_id"])}
    res = client.post(f"/api/skills/{skills['python']['skill_id']}/quiz", headers=h, json={"answers": answers}).json()
    assert res["passed"] and res["run"]["event_chain"] == ["ASSESSMENT_PASSED"]

    # coding mission: wrong first, then right
    m = _mission(client, h, "py-word-frequency")
    detail = client.get(f"/api/missions/{m['id']}", headers=h).json()
    assert "hidden_tests" not in detail and detail["hidden_test_count"] > 0
    run, sub = _submit(client, h, m["id"], "def word_frequency(text):\n    return {}\n")
    assert run["event_chain"] == ["SUBMIT_CODE", "ASSESSMENT_FAILED"] and sub["status"] in ("failed_tests", "failed_audit")
    run, sub = _submit(client, h, m["id"], PY_SOLUTION)
    assert run["event_chain"] == ["SUBMIT_CODE", "ASSESSMENT_PASSED"] and sub["status"] == "verified"
    assert client.get("/api/skills", headers=h).json()["skills"] and \
        {s["slug"]: s["tier"] for s in client.get("/api/skills", headers=h).json()["skills"]}["python"] == 2

    # applied mission: tests pass -> viva required before Tier 3
    lru = _mission(client, h, "ds-lru-cache")
    run, sub = _submit(client, h, lru["id"], LRU)
    assert run["steps"][-1]["task"] == "start_viva" and sub["status"] == "awaiting_viva"
    tiers = {s["slug"]: s["tier"] for s in client.get("/api/skills", headers=h).json()["skills"]}
    assert tiers["data-structures"] == 2  # not 3 yet
    viva = sub["viva"]
    bad = client.post(f"/api/viva/{viva['id']}/answer", headers=h, json={"answers": ["idk", "it is fast"]}).json()
    assert not bad["passed"]
    assert {s["slug"]: s["tier"] for s in client.get("/api/skills", headers=h).json()["skills"]}["data-structures"] == 2

    run, sub = _submit(client, h, lru["id"], LRU)  # fresh viva on resubmission
    good = [
        "In LRUCache.get I check whether the key is in self.entries, an OrderedDict; if missing I return -1, otherwise "
        "move_to_end marks it most recently used. put stores the value, calls move_to_end, and when len(self.entries) "
        "exceeds self.capacity popitem(last=False) evicts the least recently used key.",
        "get and put are O(1) time because OrderedDict lookups are hash based and move_to_end and popitem are constant; "
        "space is O(capacity). Edge case: capacity 1 means a second put evicts the first key so get returns -1.",
    ]
    ok = client.post(f"/api/viva/{sub['viva']['id']}/answer", headers=h, json={"answers": good}).json()
    assert ok["passed"], ok["evaluation"]
    assert {s["slug"]: s["tier"] for s in client.get("/api/skills", headers=h).json()["skills"]}["data-structures"] == 3

    # pivot preserves verified skills
    before = client.get("/api/careers/gap?role=data-scientist", headers=h).json()["match_score"]
    run = _wait_run(client, h, client.post("/api/profile/pivot", headers=h, json={"role_slug": "data-scientist"}).json()["run_id"])
    assert run["status"] == "completed"
    det = run["steps"][0]["output"]
    assert {t["skill"] for t in det["transferable"]} >= {"python", "data-structures"}
    new_rm = client.get("/api/roadmap", headers=h).json()
    assert new_rm["role"]["slug"] == "data-scientist"
    assert not any(i["skill_slug"] == "python" and i["target_tier"] <= 2 for i in new_rm["items"])  # already verified
    assert client.get("/api/careers/gap", headers=h).json()["match_score"] == before

    # analytics
    a = client.get("/api/analytics", headers=h).json()
    assert a["first_attempt"]["missions_n"] == 2 and a["tier_counts"]["3"] == 1

    # public ledger: no private data
    me = client.get("/api/auth/me", headers=h).json()
    pub = client.get(f"/api/verify/{me['public_id']}")
    assert pub.status_code == 200
    text = pub.text
    assert email not in text  # no private contact data
    assert "move_to_end" not in text  # no submitted code
    assert "It's it's" not in text and '"hidden_tests":' not in text  # no hidden test contents
    assert "BSc" not in text and "education" not in text
    body = pub.json()
    assert body["ledger"]["chain_valid"]
    assert {s["slug"] for s in body["skills"]} == {"python", "data-structures"}
    assert client.get("/api/verify/does-not-exist").status_code == 404


def test_role_based_access(client):
    r = client.post("/api/auth/register", json={"email": f"{uuid.uuid4().hex[:8]}@r.dev", "password": "password123",
                                                 "display_name": "Rec", "role": "recruiter"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.get("/api/skills", headers=h).status_code == 403
    assert client.get("/api/admin/stats", headers=h).status_code == 403
    assert client.post("/api/auth/register", json={"email": "x@y.dev", "password": "password123", "display_name": "A",
                                                    "role": "admin"}).status_code == 422
