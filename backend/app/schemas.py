from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    role: Literal["learner", "recruiter"] = "learner"  # admins are never self-registered


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    url: str = Field("", max_length=400)


class CertIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    issuer: str = Field("", max_length=200)
    year: int | None = Field(None, ge=1950, le=2100)


class ProfileIn(BaseModel):
    display_name: str | None = Field(None, max_length=120)
    headline: str | None = Field(None, max_length=200)
    education: str | None = Field(None, max_length=300)
    target_role_slug: str | None = Field(None, max_length=64)
    timeline_weeks: int | None = Field(None, ge=1, le=104)
    weekly_hours: int | None = Field(None, ge=1, le=80)
    github_repos: list[str] | None = Field(None, max_length=10)
    ledger_public: bool | None = None
    projects: list[ProjectIn] | None = Field(None, max_length=20)
    certifications: list[CertIn] | None = Field(None, max_length=20)

    @field_validator("github_repos")
    @classmethod
    def _repos(cls, v):
        if v is None:
            return v
        out = []
        for url in v:
            url = url.strip()
            if url and not url.startswith("https://github.com/"):
                raise ValueError("GitHub repositories must be https://github.com/... URLs")
            if url:
                out.append(url[:300])
        return out


class OnboardIn(BaseModel):
    claimed_skills: list[str] = Field(default_factory=list, max_length=40)


class PivotIn(BaseModel):
    role_slug: str = Field(max_length=64)


class SimulateIn(BaseModel):
    role_slug: str = Field(max_length=64)
    overrides: dict[int, int] = Field(default_factory=dict)


class QuizIn(BaseModel):
    answers: dict[int, int]


class CodeIn(BaseModel):
    language: Literal["python", "javascript", "typescript", "java"]
    code: str = Field(min_length=1, max_length=50_000)


class VivaIn(BaseModel):
    answers: list[str] = Field(min_length=1, max_length=4)

    @field_validator("answers")
    @classmethod
    def _len(cls, v):
        return [a[:4000] for a in v]


class MentorIn(BaseModel):
    message: str = Field("", max_length=4000)
    mission_id: int | None = None
    language: str | None = Field(None, max_length=16)
    code: str | None = Field(None, max_length=50_000)
    test_report: dict | None = None
    ast_report: dict | None = None
