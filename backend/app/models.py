"""Normalized schema. Works on PostgreSQL 16 (+pgvector) and SQLite."""
import secrets
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import get_settings
from .db import Base, Embedding


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _uuid() -> str:
    return uuid.uuid4().hex


def _public_id() -> str:
    return secrets.token_urlsafe(9)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    supabase_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), default="learner")  # learner|recruiter|admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    profile: Mapped["LearnerProfile | None"] = relationship(back_populates="user", uselist=False)


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, index=True, default=_public_id)
    headline: Mapped[str] = mapped_column(String(200), default="")
    education: Mapped[str] = mapped_column(String(300), default="")
    target_role_id: Mapped[int | None] = mapped_column(ForeignKey("career_roles.id"))
    timeline_weeks: Mapped[int] = mapped_column(Integer, default=12)
    weekly_hours: Mapped[int] = mapped_column(Integer, default=8)
    github_repos: Mapped[list] = mapped_column(JSON, default=list)
    ledger_public: Mapped[bool] = mapped_column(Boolean, default=True)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="profile")
    target_role: Mapped["CareerRole | None"] = relationship()
    certifications: Mapped[list["Certification"]] = relationship(cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship(cascade="all, delete-orphan")
    skills: Mapped[list["LearnerSkill"]] = relationship(cascade="all, delete-orphan", back_populates="profile")


class Certification(Base):
    __tablename__ = "certifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    issuer: Mapped[str] = mapped_column(String(200), default="")
    year: Mapped[int | None] = mapped_column(Integer)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(400), default="")


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    sfia_code: Mapped[str] = mapped_column(String(8), default="")
    aliases: Mapped[list] = mapped_column(JSON, default=list)


class SkillPrerequisite(Base):
    __tablename__ = "skill_prerequisites"
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    prereq_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)


class LearnerSkill(Base):
    __tablename__ = "learner_skills"
    __table_args__ = (UniqueConstraint("profile_id", "skill_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), index=True)
    tier: Mapped[int] = mapped_column(Integer, default=0)  # 0..3, derived from evidence only
    claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    profile: Mapped[LearnerProfile] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship()
    evidence: Mapped[list["SkillEvidence"]] = relationship(
        cascade="all, delete-orphan", order_by="SkillEvidence.created_at"
    )


class SkillEvidence(Base):
    __tablename__ = "skill_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    learner_skill_id: Mapped[int] = mapped_column(ForeignKey("learner_skills.id", ondelete="CASCADE"), index=True)
    tier: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))  # claim|github|quiz|tests|viva
    summary: Mapped[str] = mapped_column(String(400))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    ref_type: Mapped[str] = mapped_column(String(24), default="")
    ref_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CareerRole(Base):
    __tablename__ = "career_roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    onet_code: Mapped[str] = mapped_column(String(16), default="")
    sfia_level: Mapped[int] = mapped_column(Integer, default=3)
    requirements: Mapped[list["CompetencyRequirement"]] = relationship(cascade="all, delete-orphan")


class CompetencyRequirement(Base):
    __tablename__ = "competency_requirements"
    __table_args__ = (UniqueConstraint("role_id", "skill_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("career_roles.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"))
    required_tier: Mapped[int] = mapped_column(Integer, default=2)
    weight: Mapped[float] = mapped_column(Float, default=3.0)  # O*NET-style importance 1..5
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    skill: Mapped[Skill] = relationship()


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON)
    answer_index: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text, default="")


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"))
    kind: Mapped[str] = mapped_column(String(16), default="quiz")
    score: Mapped[float] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    skill: Mapped[Skill] = relationship()


class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))  # coding (Tier 2) | applied (Tier 3)
    difficulty: Mapped[str] = mapped_column(String(16), default="medium")
    brief: Mapped[str] = mapped_column(Text)
    docs: Mapped[str] = mapped_column(Text, default="")
    languages: Mapped[dict] = mapped_column(JSON)  # {lang: {starter, signature?}}
    visible_tests: Mapped[list] = mapped_column(JSON)
    hidden_tests: Mapped[list] = mapped_column(JSON)  # never serialized to clients
    ast_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    est_hours: Mapped[float] = mapped_column(Float, default=2.0)
    skill: Mapped[Skill] = relationship()


class Roadmap(Base):
    __tablename__ = "roadmaps"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("career_roles.id"))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|archived
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    items: Mapped[list["RoadmapItem"]] = relationship(
        cascade="all, delete-orphan", order_by="RoadmapItem.order_index"
    )
    role: Mapped[CareerRole] = relationship()


class RoadmapItem(Base):
    __tablename__ = "roadmap_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    roadmap_id: Mapped[int] = mapped_column(ForeignKey("roadmaps.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"))
    step: Mapped[str] = mapped_column(String(16))  # concept|coding|applied|remediation
    target_tier: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|done|archived
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    week: Mapped[int] = mapped_column(Integer, default=1)
    est_hours: Mapped[float] = mapped_column(Float, default=2.0)
    mission_id: Mapped[int | None] = mapped_column(ForeignKey("missions.id"))
    rationale: Mapped[str] = mapped_column(String(400), default="")
    resource_ids: Mapped[list] = mapped_column(JSON, default=list)
    skill: Mapped[Skill] = relationship()
    mission: Mapped[Mission | None] = relationship()


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(500), unique=True)
    source: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(24), default="docs")
    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id"))
    summary: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list | None] = mapped_column(Embedding(get_settings().embedding_dim))
    embedding_model: Mapped[str] = mapped_column(String(64), default="")


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True)
    mission_id: Mapped[int] = mapped_column(ForeignKey("missions.id"), index=True)
    language: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    # queued|running|failed_tests|failed_audit|awaiting_viva|verified|viva_failed|error
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    tests_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    test_report: Mapped[dict] = mapped_column(JSON, default=dict)
    ast_report: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_review: Mapped[dict] = mapped_column(JSON, default=dict)
    run_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    mission: Mapped[Mission] = relationship()


class VivaSession(Base):
    __tablename__ = "viva_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), unique=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True)
    questions: Mapped[list] = mapped_column(JSON)  # includes server-only grading facts
    answers: Mapped[list] = mapped_column(JSON, default=list)
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|passed|failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    submission: Mapped[Submission] = relationship()


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|completed|failed
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class AgentExecution(Base):
    __tablename__ = "agent_executions"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    agent: Mapped[str] = mapped_column(String(32))
    task: Mapped[str] = mapped_column(String(48), default="")
    status: Mapped[str] = mapped_column(String(16), default="ok")
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProgressRecord(Base):
    __tablename__ = "progress_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(32))  # quiz|submission|viva|pivot|onboard|readiness
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LedgerEntry(Base):
    """Append-only, hash-chained public proof entries. Holds only recruiter-safe data."""

    __tablename__ = "verification_ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"))
    tier: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))
    summary: Mapped[str] = mapped_column(String(400))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    entry_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    skill: Mapped[Skill] = relationship()


class MentorMessage(Base):
    __tablename__ = "mentor_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True)
    mission_id: Mapped[int | None] = mapped_column(ForeignKey("missions.id"))
    role: Mapped[str] = mapped_column(String(12))  # learner|mentor
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
