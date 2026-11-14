# SkillForge AI

**Don't just learn skills. Prove them. Become job-ready.**

SkillForge AI is a multi-agent career platform that verifies what a learner can actually do. Every
skill carries evidence and a verification tier, role readiness is scored deterministically, and the
learning plan adapts after every assessment.

## Quick start (local, no Docker)

Prerequisites: Python 3.11+, Node 20+. Java is optional (only needed to run Java missions locally).

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. On first start the backend creates the catalog and the **demo journeys**.

| Demo account (local only)          | Role      |
| ---------------------------------- | --------- |
| `maya@demo.skillforge.dev`         | Learner (backend track, Tier 1–3 evidence) |
| `leo@demo.skillforge.dev`          | Learner (pivoted frontend → full-stack)    |
| `recruiter@demo.skillforge.dev`    | Recruiter |
| `admin@demo.skillforge.dev`        | Admin     |

Password for all demo accounts: `skillforge-demo`. The login page has one-click buttons.

The demo data is **not** pre-baked. The seeder drives each journey through the real pipeline: the
agent graph, the quiz grader, sandboxed test execution, the AST audit and the Micro-Viva. Maya's
failed Algorithms quiz and her failed first bracket-matching attempt are genuine failures.

Run the tests:

```bash
cd backend
.venv/Scripts/python -m pytest -q
```

## Full stack with Docker

```bash
cp .env.example .env        # set JWT_SECRET (openssl rand -hex 32) and passwords
docker compose up --build
```

This brings up PostgreSQL 16 + pgvector, Redis, the API, an RQ worker, the Next.js frontend and a
self-hosted **Judge0** sandbox. Judge0 runs privileged and needs a Linux host with cgroup v1
(`systemd.unified_cgroup_hierarchy=0` on the kernel command line). With `APP_ENV=production` the
local subprocess runner is disabled, so Judge0 is the only code executor. Set `SEED_DEMO_DATA=true`
only for demo deployments.

## Architecture

```
Next.js 14 (App Router, Tailwind, Monaco, ReactFlow, Recharts)
   │  REST + WebSocket (/ws, live agent events)
FastAPI ── LangGraph StateGraph ──────────────────────────────┐
   │        START → orchestrator ⇄ {skill_detective, career_architect,
   │                                learning_strategist, resource_scout,
   │                                skill_validator, ai_mentor} → END
   │
   ├─ PostgreSQL 16 + pgvector (SQLite + in-process cosine as a dev fallback)
   ├─ Redis + RQ (long workflows; in-process asyncio as a fallback)
   ├─ Judge0 (isolated execution; local time-limited runner in development only)
   └─ Gemini (structured JSON; labelled deterministic fallbacks when no key)
```

### Multi-agent orchestration (`backend/app/agents`)

A hub-and-spoke LangGraph `StateGraph`. The **orchestrator** node seeds a plan from the incoming
event and re-plans after each agent reports back. For example, the Skill Validator's verdict turns
`SUBMIT_CODE` into a derived `ASSESSMENT_PASSED` or `ASSESSMENT_FAILED`, and an applied mission
swaps the debrief for `start_viva`. Agents never call each other: they read earlier agents'
structured outputs from shared state (`outputs`) and write their own. Every step is persisted to
`agent_executions` and streamed over WebSocket.

| Event | Route |
| --- | --- |
| `ONBOARD` | Skill Detective → Career Architect → Learning Strategist → Resource Scout → AI Mentor |
| `SUBMIT_CODE` | Skill Validator → (derived PASSED/FAILED chain) |
| `ASSESSMENT_PASSED` | Skill Detective (evidence) → Career Architect → Learning Strategist → AI Mentor (debrief or viva) |
| `ASSESSMENT_FAILED` | AI Mentor (diagnosis) → Resource Scout (remediation search) → Learning Strategist (insert remediation) |
| `PIVOT_GOAL` | Skill Detective (transferable) → Career Architect → Learning Strategist (re-plan, archive) → Resource Scout → AI Mentor |
| `STALLED` | Skill Detective (activity) → Learning Strategist (rebalance) → Resource Scout → AI Mentor (nudge); ends early if the learner is active |

### Verification rules

* **Tiers come only from evidence.** `skill_dna.recompute_tier` derives the tier from evidence rows.
  Claims and GitHub signals are Tier 0 and cannot raise a tier. Each evidence kind is capped:
  quiz ≤ 1, tests ≤ 2, viva ≤ 3.
* **Tier 2:** visible and hidden tests pass in the sandbox, and the static audit is clean.
* **Tier 3:** an applied mission passes its hidden tests and AST audit, then a Micro-Viva. Each viva
  answer must pass a deterministic *code-grounding* check: it must reference identifiers and concepts
  that actually occur in the submitted code, with a minimum length and no pasted code. When Gemini is
  configured, its grade is an **additional** gate. LLM judgment alone never grants Tier 3.
* **Hidden tests never leave the server.** Only test inputs go to the sandbox. Outputs are compared
  server-side, and results are read from a per-run random marker, so printed fake results cannot
  pass. Hidden failures are reported as pass/fail only.
* **Static audit:** Python `ast` for Python; Tree-sitter for JS/TS/Java (with a TypeScript-compiler
  AST fallback). It checks banned imports/calls/globals, hardcoded outputs, required patterns,
  cyclomatic complexity and nesting. Unsafe code is blocked before execution.

### Career match score (deterministic)

```
score = 100 × Σ(weight × min(verified_tier / required_tier, 1)) / Σ(weight)   over core requirements
```

Weights use the O*NET 1–5 importance scale. Skills carry SFIA 8 skill codes, and roles carry O*NET-SOC
codes and an SFIA responsibility level. These are a curated demo subset, not a licensed copy of either
framework. The simulator recomputes the same formula with what-if tiers and never saves them.

### Roadmaps, DAG and pivot

Required skills plus their transitive prerequisites form a DAG, ordered with Kahn's algorithm
(cycle-checked, ties broken by weight and criticality). Only tiers the learner has not yet verified
become tasks, so a pivot automatically preserves transferable skills. Pending tasks from the old
plan are marked `carried` or `archived`, and the old roadmap is archived, never deleted.

### Proof-of-Skill ledger

`/verify/:public_id` shows only Tier 1+ ledger entries. Each entry is SHA-256 hash-chained to the
previous one, and the page recomputes the chain to show integrity. The page never includes email,
education, code, hidden tests or viva answers. Learners can switch it off (`ledger_public`).

## Environment variables

See `backend/.env.example`, `frontend/.env.local.example` and `.env.example` (compose). Everything
is optional in development. In production, `JWT_SECRET` is required, and you should configure
`DATABASE_URL` (Postgres), `JUDGE0_URL`, `REDIS_URL` and optionally `GEMINI_API_KEY` and Supabase.

## Fallbacks (shown on the admin dashboard)

| Integration | Production | Fallback (labelled in the UI) |
| --- | --- | --- |
| LLM | Gemini structured JSON | deterministic templates / metric-based review |
| Embeddings | Gemini embeddings | hashed n-gram embeddings (`hash-v1`) |
| Vector search | pgvector HNSW | in-process cosine |
| Execution | Judge0 | local time-limited subprocess (**dev only, not a sandbox**) |
| Queue | Redis + RQ | in-process asyncio task |
| Database | PostgreSQL 16 | SQLite |

## Project layout

```
backend/app/
  agents/      LangGraph graph, shared state, agent task handlers
  api/         REST routers (auth, learner, missions, public/admin/ws)
  services/    skill_dna, career, roadmap, resources, sandbox, static_analysis, review, mentor, llm
  seed_data.py catalog: skills, prerequisites, roles, quizzes, missions (+hidden tests), resources
  seed.py      catalog seeding + real-pipeline demo journeys
backend/migrations/  Alembic
backend/tests/       engine unit tests + end-to-end API journey
frontend/src/app/    landing, auth, onboarding, dashboard, skills, career, roadmap, missions/[id] (IDE),
                     mentor, analytics, agents, verify/[id], recruiter, admin
```
