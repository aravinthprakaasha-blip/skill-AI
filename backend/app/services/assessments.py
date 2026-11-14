"""Concept quizzes (Tier 1). Answers are graded server-side; correct indices never reach the client."""
from sqlalchemy.orm import Session

from ..models import Assessment, QuizQuestion, Skill

PASS_PCT = 75.0


def public_quiz(db: Session, skill: Skill) -> dict:
    qs = db.query(QuizQuestion).filter_by(skill_id=skill.id).order_by(QuizQuestion.id).all()
    return {
        "skill": {"id": skill.id, "slug": skill.slug, "name": skill.name},
        "pass_pct": PASS_PCT,
        "questions": [{"id": q.id, "prompt": q.prompt, "options": q.options} for q in qs],
    }


def grade(db: Session, profile_id: str, skill: Skill, answers: dict[int, int]) -> Assessment:
    qs = db.query(QuizQuestion).filter_by(skill_id=skill.id).order_by(QuizQuestion.id).all()
    if not qs:
        raise ValueError("No quiz exists for this skill")
    detail, correct = [], 0
    for q in qs:
        given = answers.get(q.id)
        ok = given == q.answer_index
        correct += ok
        detail.append({"id": q.id, "prompt": q.prompt, "given": given, "correct": ok,
                       "answer_index": q.answer_index, "explanation": q.explanation})
    score = round(100 * correct / len(qs), 1)
    attempts = db.query(Assessment).filter_by(profile_id=profile_id, skill_id=skill.id, kind="quiz").count()
    a = Assessment(profile_id=profile_id, skill_id=skill.id, kind="quiz", score=score, passed=score >= PASS_PCT,
                   attempt_no=attempts + 1, detail={"correct": correct, "total": len(qs), "questions": detail})
    db.add(a)
    db.flush()
    return a
