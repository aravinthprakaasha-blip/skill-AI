import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="sf_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'test.db')}"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["GEMINI_API_KEY"] = ""
os.environ["JUDGE0_URL"] = ""
os.environ["REDIS_URL"] = ""
os.environ["JWT_SECRET"] = "test-secret-0123456789-abcdefghijklmnop"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(client):
    from app.db import SessionLocal

    s = SessionLocal()
    yield s
    s.close()
