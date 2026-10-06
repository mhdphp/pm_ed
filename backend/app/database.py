import sqlite3
from typing import Iterable, Literal

from app.config import DEFAULT_BOARD_TITLE, INITIAL_COLUMNS, get_db_path

VALID_TABLES = {"cards", "columns"}


def connect_db() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = connect_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS boards (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT 'My Board',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE (user_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS columns (
            id INTEGER PRIMARY KEY,
            board_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            position INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (board_id) REFERENCES boards(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY,
            column_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (column_id) REFERENCES columns(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_boards_user_id ON boards(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_columns_board_id ON columns(board_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_column_id ON cards(column_id)")
    conn.commit()
    conn.close()


def get_or_create_user(conn: sqlite3.Connection, username: str) -> int:
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        return int(row["id"])
    cursor = conn.execute("INSERT INTO users (username) VALUES (?)", (username,))
    conn.commit()
    return int(cursor.lastrowid)


def get_or_create_board(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute("SELECT id FROM boards WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return int(row["id"])
    cursor = conn.execute(
        "INSERT INTO boards (user_id, title) VALUES (?, ?)",
        (user_id, DEFAULT_BOARD_TITLE),
    )
    conn.commit()
    return int(cursor.lastrowid)


def ensure_seed_data(conn: sqlite3.Connection, user_id: int) -> int:
    board_id = get_or_create_board(conn, user_id)
    column_count = conn.execute(
        "SELECT COUNT(*) AS count FROM columns WHERE board_id = ?",
        (board_id,),
    ).fetchone()["count"]
    if column_count:
        return board_id

    for column_index, (column_title, cards) in enumerate(INITIAL_COLUMNS):
        column_cursor = conn.execute(
            "INSERT INTO columns (board_id, title, position) VALUES (?, ?, ?)",
            (board_id, column_title, column_index),
        )
        column_id = int(column_cursor.lastrowid)
        for card_index, (title, details) in enumerate(cards):
            conn.execute(
                "INSERT INTO cards (column_id, title, details, position) VALUES (?, ?, ?, ?)",
                (column_id, title, details, card_index),
            )
    conn.commit()
    return board_id


def fetch_board(conn: sqlite3.Connection, user_id: int) -> dict:
    board_id = ensure_seed_data(conn, user_id)
    board_row = conn.execute(
        "SELECT id, title FROM boards WHERE id = ?",
        (board_id,),
    ).fetchone()

    column_rows = conn.execute(
        "SELECT id, title, position FROM columns WHERE board_id = ? ORDER BY position",
        (board_id,),
    ).fetchall()

    card_rows = conn.execute(
        """
        SELECT id, column_id, title, details, position
        FROM cards
        WHERE archived = 0 AND column_id IN (
            SELECT id FROM columns WHERE board_id = ?
        )
        ORDER BY column_id, position
        """,
        (board_id,),
    ).fetchall()

    cards_by_id = {
        str(row["id"]): {
            "id": str(row["id"]),
            "title": row["title"],
            "details": row["details"],
        }
        for row in card_rows
    }

    cards_by_column: dict[int, list[str]] = {int(row["id"]): [] for row in column_rows}
    for row in card_rows:
        cards_by_column[int(row["column_id"])].append(str(row["id"]))

    columns_payload = [
        {
            "id": str(row["id"]),
            "title": row["title"],
            "position": row["position"],
            "cardIds": cards_by_column.get(int(row["id"]), []),
        }
        for row in column_rows
    ]

    return {
        "board": {"id": str(board_row["id"]), "title": board_row["title"]},
        "columns": columns_payload,
        "cards": cards_by_id,
    }


def ordered_ids(rows: Iterable[sqlite3.Row]) -> list[int]:
    return [int(row["id"]) for row in rows]


def resequence_positions(
    conn: sqlite3.Connection,
    table: Literal["cards", "columns"],
    ids: list[int],
    extra_where: str,
    extra_params: tuple,
) -> None:
    if table not in VALID_TABLES:
        raise ValueError(f"Invalid table: {table}")
    for index, item_id in enumerate(ids):
        conn.execute(
            f"UPDATE {table} SET position = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? {extra_where}",
            (index, item_id, *extra_params),
        )


def clamp_position(position: int | None, length: int) -> int:
    if position is None:
        return length
    return max(0, min(position, length))


def get_owned_column(conn: sqlite3.Connection, column_id: int, board_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id FROM columns WHERE id = ? AND board_id = ?",
        (column_id, board_id),
    ).fetchone()


def get_owned_card(conn: sqlite3.Connection, card_id: int, board_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT cards.id, cards.column_id
        FROM cards
        JOIN columns ON cards.column_id = columns.id
        WHERE cards.id = ? AND columns.board_id = ?
        """,
        (card_id, board_id),
    ).fetchone()


def column_card_ids(conn: sqlite3.Connection, column_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM cards WHERE column_id = ? AND archived = 0 ORDER BY position",
        (column_id,),
    ).fetchall()
    return ordered_ids(rows)


def insert_card(
    conn: sqlite3.Connection, column_id: int, title: str, details: str, position: int | None
) -> int:
    ids = column_card_ids(conn, column_id)
    insert_position = clamp_position(position, len(ids))
    cursor = conn.execute(
        "INSERT INTO cards (column_id, title, details, position) VALUES (?, ?, ?, ?)",
        (column_id, title, details, insert_position),
    )
    card_id = int(cursor.lastrowid)
    ids.insert(insert_position, card_id)
    resequence_positions(conn, "cards", ids, "AND column_id = ?", (column_id,))
    return card_id


def update_card_fields(
    conn: sqlite3.Connection, card_id: int, title: str | None, details: str | None
) -> None:
    if title is not None:
        conn.execute(
            "UPDATE cards SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (title, card_id),
        )
    if details is not None:
        conn.execute(
            "UPDATE cards SET details = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (details, card_id),
        )


def move_card(
    conn: sqlite3.Connection,
    card_id: int,
    source_column_id: int,
    target_column_id: int,
    position: int | None,
) -> None:
    source_ids = column_card_ids(conn, source_column_id)
    source_ids.remove(card_id)
    if target_column_id == source_column_id:
        target_ids = source_ids
    else:
        target_ids = column_card_ids(conn, target_column_id)
    target_ids.insert(clamp_position(position, len(target_ids)), card_id)

    conn.execute(
        "UPDATE cards SET column_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (target_column_id, card_id),
    )
    if target_column_id != source_column_id:
        resequence_positions(conn, "cards", source_ids, "AND column_id = ?", (source_column_id,))
    resequence_positions(conn, "cards", target_ids, "AND column_id = ?", (target_column_id,))


def delete_card(conn: sqlite3.Connection, card_id: int, column_id: int) -> None:
    conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    resequence_positions(
        conn, "cards", column_card_ids(conn, column_id), "AND column_id = ?", (column_id,)
    )
