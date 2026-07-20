import os
import shutil
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH, DB_SEED_PATH

TABLES = """
CREATE TABLE IF NOT EXISTS game_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    source TEXT NOT NULL,
    team_key TEXT NOT NULL,
    lane TEXT NOT NULL,
    champion TEXT NOT NULL,
    win INTEGER NOT NULL,
    patch TEXT,
    UNIQUE(game_id, team_key, champion)
);

CREATE TABLE IF NOT EXISTS processed_matches (
    match_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS champion_bans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    source TEXT NOT NULL,
    champion TEXT NOT NULL,
    patch TEXT,
    UNIQUE(game_id, champion)
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_gp_champion ON game_participants (champion);
CREATE INDEX IF NOT EXISTS idx_gp_team_key ON game_participants (team_key);
CREATE INDEX IF NOT EXISTS idx_gp_game_id ON game_participants (game_id);
CREATE INDEX IF NOT EXISTS idx_gp_lane_champion ON game_participants (lane, champion);
CREATE INDEX IF NOT EXISTS idx_gp_patch ON game_participants (patch);
CREATE INDEX IF NOT EXISTS idx_bans_champion ON champion_bans (champion);
CREATE INDEX IF NOT EXISTS idx_bans_source ON champion_bans (source);
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
        conn.executescript(TABLES)
        _migrate(conn)
        conn.executescript(INDEXES)


def _migrate(conn):
    """이미 만들어진 DB에 새로 추가된 컬럼을 뒤늦게 채워 넣는다 (기존 데이터는 유지)."""
    cols = [row["name"] for row in conn.execute("PRAGMA table_info(game_participants)").fetchall()]
    if "patch" not in cols:
        conn.execute("ALTER TABLE game_participants ADD COLUMN patch TEXT")


def is_match_processed(conn, match_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM processed_matches WHERE match_id = ?", (match_id,)).fetchone()
    return row is not None


def mark_match_processed(conn, match_id: str):
    conn.execute("INSERT OR IGNORE INTO processed_matches (match_id) VALUES (?)", (match_id,))


def insert_participant(
    conn, game_id: str, source: str, team_key: str, lane: str, champion: str, win: bool, patch: str | None = None
):
    conn.execute(
        """
        INSERT OR IGNORE INTO game_participants (game_id, source, team_key, lane, champion, win, patch)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (game_id, source, team_key, lane, champion, int(win), patch),
    )


def insert_ban(conn, game_id: str, source: str, champion: str, patch: str | None = None):
    conn.execute(
        """
        INSERT OR IGNORE INTO champion_bans (game_id, source, champion, patch)
        VALUES (?, ?, ?, ?)
        """,
        (game_id, source, champion, patch),
    )
