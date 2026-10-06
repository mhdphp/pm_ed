import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db
import app.ai as ai_module


class _DummyResponse:
    def __init__(self, content: str) -> None:
        self.status_code = 200
        self._content = content

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": self._content,
                    }
                }
            ]
        }


def _make_client(tmp_path: Path) -> TestClient:
    os.environ["PM_DB_PATH"] = str(tmp_path / "test.db")
    init_db()
    return TestClient(app)


def test_chat_applies_actions(monkeypatch, tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    board = client.get("/api/board").json()
    column_id = board["columns"][0]["id"]

    response_content = json.dumps(
        {
            "reply": "Created a card.",
            "actions": [
                {
                    "type": "create_card",
                    "columnId": column_id,
                    "title": "AI created",
                    "details": "",
                    "position": 0,
                }
            ],
        }
    )

    def _mock_post(*_args, **_kwargs):
        return _DummyResponse(response_content)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(ai_module.httpx, "post", _mock_post)

    response = client.post("/api/chat", json={"message": "Add a card."})
    assert response.status_code == 200

    payload = response.json()
    assert payload["response"] == "Created a card."
    assert payload["actions"][0]["type"] == "create_card"

    updated_board = payload["board"]
    assert any(card["title"] == "AI created" for card in updated_board["cards"].values())


def test_chat_returns_502_for_invalid_model_output(monkeypatch, tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        ai_module.httpx, "post", lambda *_a, **_k: _DummyResponse('{"actions": []}')
    )

    response = client.post("/api/chat", json={"message": "Hi"})
    assert response.status_code == 502


def test_chat_requests_json_schema_output(monkeypatch, tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    captured = {}

    def _mock_post(*_args, **kwargs):
        captured.update(kwargs["json"])
        return _DummyResponse('{"reply": "Hi", "actions": []}')

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(ai_module.httpx, "post", _mock_post)

    response = client.post("/api/chat", json={"message": "Hi"})
    assert response.status_code == 200
    assert captured["response_format"]["type"] == "json_schema"
