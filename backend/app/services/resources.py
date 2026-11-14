"""Curated resource retrieval via vector search (pgvector on PostgreSQL, in-process cosine otherwise)."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import engine
from ..models import Resource
from . import llm


def _doc(r: Resource) -> str:
    return f"{r.title}. {r.summary} Source: {r.source}."


async def index_all(db: Session) -> int:
    """Embed resources that are missing a vector or were embedded with a different model."""
    model = llm.embedding_model_name()
    n = 0
    for r in db.query(Resource).filter((Resource.embedding.is_(None)) | (Resource.embedding_model != model)):
        r.embedding, r.embedding_model = await llm.embed(_doc(r))
        n += 1
    db.flush()
    return n


def _row(r: Resource, score: float) -> dict:
    return {
        "id": r.id,
        "title": r.title,
        "url": r.url,
        "source": r.source,
        "kind": r.kind,
        "summary": r.summary,
        "skill_id": r.skill_id,
        "score": round(float(score), 4),
    }


async def search(db: Session, query: str, skill_id: int | None = None, k: int = 4) -> list[dict]:
    qvec, model = await llm.embed(query)
    boost = 0.15  # same-skill resources get a fixed, documented boost
    if engine.dialect.name == "postgresql":
        lit = "[" + ",".join(f"{v:.6f}" for v in qvec) + "]"
        rows = db.execute(
            text(
                "SELECT id, 1 - (embedding <=> CAST(:q AS vector)) AS sim FROM resources "
                "WHERE embedding IS NOT NULL AND embedding_model = :m "
                "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :n"
            ),
            {"q": lit, "m": model, "n": max(k * 5, 20)},
        ).all()
        by_id = {r.id: r for r in db.query(Resource).filter(Resource.id.in_([x.id for x in rows]))}
        scored = [(by_id[x.id], float(x.sim)) for x in rows if x.id in by_id]
    else:
        scored = [
            (r, llm.cosine(qvec, r.embedding))
            for r in db.query(Resource).filter(Resource.embedding_model == model)
            if r.embedding
        ]
    ranked = sorted(
        ((r, s + (boost if skill_id and r.skill_id == skill_id else 0)) for r, s in scored),
        key=lambda x: (-x[1], x[0].id),
    )
    return [_row(r, s) for r, s in ranked[:k]]
