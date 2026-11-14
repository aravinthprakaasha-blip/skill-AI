from contextlib import contextmanager

from sqlalchemy import JSON, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import get_settings

settings = get_settings()

_url = settings.database_url
for _prefix in ("postgresql://", "postgres://"):
    if _url.startswith(_prefix):
        _url = _url.replace(_prefix, "postgresql+psycopg://", 1)

_kwargs: dict = {"pool_pre_ping": True}
if _url.startswith("sqlite"):
    _kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in _url or _url.endswith("://"):
        from sqlalchemy.pool import StaticPool

        _kwargs["poolclass"] = StaticPool

engine = create_engine(_url, **_kwargs)

if _url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):  # enforce foreign keys on SQLite
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Embedding(TypeDecorator):
    """pgvector `vector(dim)` on PostgreSQL, JSON array elsewhere."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 768):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_result_value(self, value, dialect):
        return None if value is None else [float(x) for x in value]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401

    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_resources_embedding_hnsw ON resources USING hnsw (embedding vector_cosine_ops)"
            )
            lock_down_tables(conn)


def lock_down_tables(conn) -> None:
    """Enable Row Level Security (with no policies) on every SkillForge table.

    Hosted Postgres such as Supabase exposes the `public` schema through an auto-generated REST
    API reachable with the public anon key. RLS without policies denies that API all access. The
    backend connects as the table owner, which bypasses RLS, so the application is unaffected.
    """
    for table in Base.metadata.sorted_tables:
        conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
    conn.exec_driver_sql("ALTER TABLE IF EXISTS alembic_version ENABLE ROW LEVEL SECURITY")
