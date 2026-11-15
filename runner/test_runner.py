import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("RUNNER_TOKEN", "t0ken")
    monkeypatch.setenv("RUNNER_TIME_LIMIT_S", "2")
    import main

    importlib.reload(main)
    return TestClient(main.app)


H = {"X-Runner-Token": "t0ken"}


def test_requires_token(client):
    r = client.post("/run", json={"language": "python", "source": "print(1)"})
    assert r.status_code == 401
    assert client.post("/run", headers={"X-Runner-Token": "wrong"}, json={"language": "python", "source": "print(1)"}).status_code == 401


def test_runs_python_with_stdin(client):
    r = client.post("/run", headers=H, json={"language": "python", "source": "import sys\nprint(sys.stdin.read().upper())", "stdin": "hi"})
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["stdout"].strip() == "HI"


def test_runtime_error_and_env_scrubbed(client, monkeypatch):
    r = client.post("/run", headers=H, json={"language": "python", "source": "import os\nprint(os.environ.get('RUNNER_TOKEN'))\nraise SystemExit(3)"})
    body = r.json()
    assert body["status"] == "runtime_error"
    assert "t0ken" not in body["stdout"]  # the service's own secret is not visible to submissions


def test_timeout_kills_infinite_loop(client):
    r = client.post("/run", headers=H, json={"language": "python", "source": "while True:\n    pass"})
    assert r.json()["status"] == "timeout"


def test_javascript(client):
    r = client.post("/run", headers=H, json={"language": "javascript", "source": "console.log(6*7)"})
    assert r.json()["stdout"].strip() == "42"


def test_rejects_unknown_language(client):
    assert client.post("/run", headers=H, json={"language": "cobol", "source": "x"}).status_code == 422
