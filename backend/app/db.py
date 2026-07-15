import os
import shutil
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH, DB_SEED_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS game_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    source TEXT NOT NULL,
    team_key TEXT NOT NULL,
    lane TEXT NOT NULL,
    champion TEXT NOT NULL,
    win INTEGER NOT NULL,
    UNIQUE(game_id, team_key, champion)
);

CREATE TABLE IF NOT EXISTS processed_matches (
    match_id TEXT PRIMARY KEY
);

CREATE INDEX IF NOT EXISTS idx_gp_champion ON game_participants (champion);
CREATE INDEX IF NOT EXISTS idx_gp_team_key ON game_participants (team_key);
CREATE INDEX IF NOT EXISTS idx_gp_game_id ON game_participants (game_id);
CREATE INDEX IF NOT EXISTS idx_gp_lane_champion ON game_participants (lane, champion);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    if not os.path.exists(DB_PATH) and os.path.exists(DB_SEED_PATH):
        shutil.copyfile(DB_SEED_PATH, DB_PATH)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def is_match_processed(conn, match_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM processed_matches WHERE match_id = ?", (match_id,)).fetchone()
    return row is not None


def mark_match_processed(conn, match_id: str):
    conn.execute("INSERT OR IGNORE INTO processed_matches (match_id) VALUES (?)", (match_id,))


def insert_participant(conn, game_id: str, source: str, team_key: str, lane: str, champion: str, win: bool):
    conn.execute(
        """
        INSERT OR IGNORE INTO game_participants (game_id, source, team_key, lane, champion, win)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (game_id, source, team_key, lane, champion, int(win)),
    )
