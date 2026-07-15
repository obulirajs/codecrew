"""
Smoke test for story 0.5. Requires a valid .env (or env vars) to be present
for the "ok" path - run `pytest` from inside backend/ after copying
.env.example to .env with real values.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "dependencies" in body
