import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.database import (
    clamp_position,
    delete_card,
    fetch_board,
    get_or_create_board,
    get_or_create_user,
    get_owned_card,
    get_owned_column,
    insert_card,
    move_card,
    ordered_ids,
    resequence_positions,
    update_card_fields,
)
from app.dependencies import get_db, get_username
from app.models import CardCreate, CardUpdate, ColumnCreate, ColumnUpdate

router = APIRouter()


def _board_column_ids(conn: sqlite3.Connection, board_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM columns WHERE board_id = ? ORDER BY position",
        (board_id,),
    ).fetchall()
    return ordered_ids(rows)


@router.get("/api/board")
def get_board(
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    return fetch_board(conn, user_id)


@router.post("/api/columns")
def create_column(
    payload: ColumnCreate,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    ids = _board_column_ids(conn, board_id)
    insert_position = clamp_position(payload.position, len(ids))
    cursor = conn.execute(
        "INSERT INTO columns (board_id, title, position) VALUES (?, ?, ?)",
        (board_id, payload.title, insert_position),
    )
    column_id = int(cursor.lastrowid)
    ids.insert(insert_position, column_id)
    resequence_positions(conn, "columns", ids, "AND board_id = ?", (board_id,))
    conn.commit()

    return {"id": str(column_id)}


@router.patch("/api/columns/{column_id}")
def update_column(
    column_id: int,
    payload: ColumnUpdate,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    if not get_owned_column(conn, column_id, board_id):
        raise HTTPException(status_code=404, detail="Column not found")

    if payload.title is not None:
        conn.execute(
            "UPDATE columns SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (payload.title, column_id),
        )

    if payload.position is not None:
        ids = _board_column_ids(conn, board_id)
        ids.remove(column_id)
        ids.insert(clamp_position(payload.position, len(ids)), column_id)
        resequence_positions(conn, "columns", ids, "AND board_id = ?", (board_id,))

    conn.commit()
    return {"status": "ok"}


@router.delete("/api/columns/{column_id}")
def delete_column(
    column_id: int,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    if not get_owned_column(conn, column_id, board_id):
        raise HTTPException(status_code=404, detail="Column not found")

    conn.execute("DELETE FROM cards WHERE column_id = ?", (column_id,))
    conn.execute("DELETE FROM columns WHERE id = ?", (column_id,))
    resequence_positions(
        conn, "columns", _board_column_ids(conn, board_id), "AND board_id = ?", (board_id,)
    )
    conn.commit()

    return {"status": "ok"}


@router.post("/api/cards")
def create_card(
    payload: CardCreate,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    if not get_owned_column(conn, payload.column_id, board_id):
        raise HTTPException(status_code=404, detail="Column not found")

    card_id = insert_card(conn, payload.column_id, payload.title, payload.details, payload.position)
    conn.commit()

    return {"id": str(card_id)}


@router.patch("/api/cards/{card_id}")
def update_card(
    card_id: int,
    payload: CardUpdate,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    card = get_owned_card(conn, card_id, board_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    current_column_id = int(card["column_id"])
    target_column_id = payload.column_id or current_column_id
    if payload.column_id is not None and not get_owned_column(conn, payload.column_id, board_id):
        raise HTTPException(status_code=404, detail="Column not found")

    update_card_fields(conn, card_id, payload.title, payload.details)
    if payload.position is not None or target_column_id != current_column_id:
        move_card(conn, card_id, current_column_id, target_column_id, payload.position)

    conn.commit()
    return {"status": "ok"}


@router.delete("/api/cards/{card_id}")
def delete_card_route(
    card_id: int,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    card = get_owned_card(conn, card_id, board_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    delete_card(conn, card_id, int(card["column_id"]))
    conn.commit()
    return {"status": "ok"}
