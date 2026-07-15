import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS matchups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    lane TEXT NOT NULL,
    champion TEXT NOT NULL,
    enemy_champion TEXT NOT NULL,
    win INTEGER NOT NULL,
    UNIQUE(match_id, lane, champion)
);

CREATE TABLE IF NOT EXISTS processed_matches (
    match_id TEXT PRIMARY KEY
);

CREATE INDEX IF NOT EXISTS idx_matchups_lookup
    ON matchups (lane, enemy_champion, champion);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def is_match_processed(conn, match_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM processed_matches WHERE match_id = ?", (match_id,)).fetchone()
    return row is not None


def mark_match_processed(conn, match_id: str):
    conn.execute("INSERT OR IGNORE INTO processed_matches (match_id) VALUES (?)", (match_id,))


def insert_matchup(conn, match_id: str, lane: str, champion: str, enemy_champion: str, win: bool):
    conn.execute(
        """
        INSERT OR IGNORE INTO matchups (match_id, lane, champion, enemy_champion, win)
        VALUES (?, ?, ?, ?, ?)
        """,
        (match_id, lane, champion, enemy_champion, int(win)),
    )
