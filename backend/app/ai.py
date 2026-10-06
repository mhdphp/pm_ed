import json
import sqlite3

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import (
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    OPENROUTER_TEMPERATURE,
    get_openrouter_api_key,
)
from app.database import (
    delete_card,
    get_or_create_board,
    get_owned_card,
    get_owned_column,
    insert_card,
    move_card,
    update_card_fields,
)
from app.models import (
    ChatHistoryItem,
    CreateCardAction,
    DeleteCardAction,
    MoveCardAction,
    StructuredChatOutput,
    UpdateCardAction,
    ChatAction,
)

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "kanban_ai_response",
        "strict": False,
        "schema": StructuredChatOutput.model_json_schema(),
    },
}


def parse_structured_output(content: str) -> StructuredChatOutput:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        trimmed = content.strip()
        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(trimmed[start : end + 1])
            except json.JSONDecodeError as inner_exc:
                raise HTTPException(
                    status_code=502, detail="OpenRouter returned invalid JSON"
                ) from inner_exc
        else:
            raise HTTPException(status_code=502, detail="OpenRouter returned invalid JSON") from exc
    try:
        return StructuredChatOutput.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502, detail="OpenRouter returned an invalid response"
        ) from exc


def call_openrouter(messages: list[dict[str, str]]) -> tuple[str, str | None]:
    api_key = get_openrouter_api_key()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not configured")

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": OPENROUTER_TEMPERATURE,
        "response_format": RESPONSE_FORMAT,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=20,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="OpenRouter request failed") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="OpenRouter returned an error")

    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="OpenRouter returned invalid JSON") from exc
    choices = data.get("choices", [])
    if not choices:
        raise HTTPException(status_code=502, detail="OpenRouter response missing choices")
    message_data = choices[0].get("message")
    if not message_data or "content" not in message_data:
        raise HTTPException(status_code=502, detail="OpenRouter response missing content")
    return str(message_data["content"]).strip(), data.get("model")


def build_structured_messages(
    board: dict, history: list[ChatHistoryItem], message: str
) -> list[dict[str, str]]:
    summary_parts = []
    column_titles = []
    columns = board.get("columns", [])
    cards = board.get("cards", {})
    for column in columns:
        column_titles.append(str(column.get("title")))
        card_titles = [
            cards[card_id]["title"]
            for card_id in column.get("cardIds", [])
            if card_id in cards
        ]
        summary_parts.append(
            f"{column.get('title')}: {', '.join(card_titles) if card_titles else 'No cards'}"
        )
    board_summary = " | ".join(summary_parts)
    column_summary = ", ".join(column_titles)
    schema_hint = (
        "You are a Kanban assistant. Reply only as JSON with this shape:\n"
        '{"reply": string, "actions": [action, ...]}\n'
        "Keep replies concise (1-2 sentences) unless the user requests detail.\n"
        "Board data is ALWAYS provided below. Never claim you lack board data.\n"
        "If asked to summarize the project or board, use ONLY the provided board data.\n"
        "List the columns exactly as provided and mention a few key cards. Do not invent columns or cards.\n"
        "Action types:\n"
        '- create_card: {"type": "create_card", "columnId": string, "title": string, '
        '"details": string, "position": number|null}\n'
        '- update_card: {"type": "update_card", "cardId": string, "title": string|null, '
        '"details": string|null}\n'
        '- move_card: {"type": "move_card", "cardId": string, "columnId": string, '
        '"position": number|null}\n'
        '- delete_card: {"type": "delete_card", "cardId": string}\n'
        "Do not include any extra keys or text.\n\n"
        f"Board columns (authoritative): {column_summary}\n"
        f"Board summary (authoritative): {board_summary}\n"
        f"Current board data (JSON):\n{json.dumps(board, indent=2)}"
    )
    messages_list = [{"role": "system", "content": schema_hint}]
    for item in history:
        messages_list.append({"role": item.role, "content": item.content})
    messages_list.append({"role": "user", "content": message})
    return messages_list


def _parse_id(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def apply_actions(
    conn: sqlite3.Connection, user_id: int, actions: list[ChatAction]
) -> None:
    board_id = get_or_create_board(conn, user_id)

    for action in actions:
        if isinstance(action, CreateCardAction):
            column_id = _parse_id(action.columnId)
            if column_id is None or not get_owned_column(conn, column_id, board_id):
                continue
            insert_card(conn, column_id, action.title, action.details, action.position)
            continue

        card_id = _parse_id(action.cardId)
        card = get_owned_card(conn, card_id, board_id) if card_id is not None else None
        if not card:
            continue

        if isinstance(action, UpdateCardAction):
            update_card_fields(conn, card_id, action.title, action.details)
        elif isinstance(action, MoveCardAction):
            target_column_id = _parse_id(action.columnId)
            if target_column_id is None or not get_owned_column(conn, target_column_id, board_id):
                continue
            move_card(conn, card_id, int(card["column_id"]), target_column_id, action.position)
        elif isinstance(action, DeleteCardAction):
            delete_card(conn, card_id, int(card["column_id"]))

    conn.commit()
