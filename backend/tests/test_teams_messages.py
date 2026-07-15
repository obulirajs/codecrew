"""
Verifies the non-message activity filter added to /teams/messages: Web Chat
sends a "typing" activity on every keystroke, and those must never reach the
orchestrator or trigger a reply.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_typing_activity_is_ignored():
    typing_payload = {
        "type": "typing",
        "from": {"id": "x"},
        "conversation": {"id": "y"},
    }

    with patch("app.main.orchestrator_graph") as mock_graph, patch(
        "app.main.send_reply"
    ) as mock_send_reply:
        response = client.post("/teams/messages", json=typing_payload)

    assert response.status_code == 200
    body = response.json()
    assert body == {"received": True, "ignored": True, "activity_type": "typing"}

    mock_graph.invoke.assert_not_called()
    mock_send_reply.assert_not_called()
