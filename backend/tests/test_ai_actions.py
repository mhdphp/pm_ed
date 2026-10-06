import os
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.ai import apply_actions, parse_structured_output
from app.database import connect_db, fetch_board, get_or_create_user, init_db
from app.models import CreateCardAction, DeleteCardAction, MoveCardAction, UpdateCardAction


def test_parse_structured_output() -> None:
    import json
    content = json.dumps(
        {
            "reply": "All set.",
            "actions": [
                {
                    "type": "create_card",
                    "columnId": "1",
                    "title": "New card",
                    "details": "Details",
                    "position": 0,
                }
            ],
        }
    )

    parsed = parse_structured_output(content)
    assert parsed.reply == "All set."
    assert parsed.actions
    assert parsed.actions[0].type == "create_card"


def test_apply_actions_updates_board(tmp_path: Path) -> None:
    os.environ["PM_DB_PATH"] = str(tmp_path / "test.db")
    init_db()

    conn = connect_db()
    user_id = get_or_create_user(conn, "user")
    board = fetch_board(conn, user_id)

    first_column = board["columns"][0]
    second_column = board["columns"][1]
    first_card_id = board["columns"][0]["cardIds"][0]

    actions = [
        CreateCardAction(
            type="create_card",
            columnId=first_column["id"],
            title="AI card",
            details="",
            position=0,
        ),
        MoveCardAction(
            type="move_card",
            cardId=first_card_id,
            columnId=second_column["id"],
            position=0,
        ),
        UpdateCardAction(
            type="update_card",
            cardId=first_card_id,
            title="Updated title",
        ),
        DeleteCardAction(
            type="delete_card",
            cardId=first_card_id,
        ),
    ]

    apply_actions(conn, user_id, actions)
    updated = fetch_board(conn, user_id)

    assert any(card["title"] == "AI card" for card in updated["cards"].values())
    assert first_card_id not in updated["cards"]
    conn.close()


def test_parse_structured_output_extracts_wrapped_json() -> None:
    parsed = parse_structured_output('Sure: {"reply": "Done.", "actions": []} thanks')
    assert parsed.reply == "Done."


@pytest.mark.parametrize(
    "content",
    [
        "not json at all",
        '{"actions": []}',
        '{"reply": "x", "actions": [{"type": "rename_column"}]}',
    ],
)
def test_parse_structured_output_rejects_invalid(content: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        parse_structured_output(content)
    assert exc_info.value.status_code == 502


def test_apply_actions_skips_invalid_targets(tmp_path: Path) -> None:
    os.environ["PM_DB_PATH"] = str(tmp_path / "test.db")
    init_db()

    conn = connect_db()
    user_id = get_or_create_user(conn, "user")
    before = fetch_board(conn, user_id)
    first_card_id = before["columns"][0]["cardIds"][0]

    actions = [
        CreateCardAction(type="create_card", columnId="Backlog", title="Bad column"),
        CreateCardAction(type="create_card", columnId="9999", title="Missing column"),
        DeleteCardAction(type="delete_card", cardId="card-1"),
        UpdateCardAction(type="update_card", cardId="9999", title="Missing card"),
        MoveCardAction(type="move_card", cardId=first_card_id, columnId="Done"),
    ]

    apply_actions(conn, user_id, actions)
    assert fetch_board(conn, user_id) == before
    conn.close()
