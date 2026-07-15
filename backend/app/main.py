from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import LANES
from .db import get_conn, init_db

app = FastAPI(title="LoL Ban/Pick Helper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/lanes")
def get_lanes():
    return LANES


@app.get("/api/champions")
def get_champions():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT champion FROM matchups ORDER BY champion"
        ).fetchall()
    return [row["champion"] for row in rows]


@app.get("/api/recommend")
def recommend(
    lane: str = Query(..., description="TOP / JUNGLE / MIDDLE / BOTTOM / UTILITY"),
    enemy_champion: str = Query(..., description="상대 챔피언 이름 (영문, 예: Darius)"),
    min_games: int = Query(5, ge=1, description="최소 표본 게임 수"),
):
    lane = lane.upper()
    if lane not in LANES:
        raise HTTPException(status_code=400, detail=f"lane은 {LANES} 중 하나여야 합니다")

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT champion,
                   COUNT(*) AS games,
                   SUM(win) AS wins
            FROM matchups
            WHERE lane = ? AND enemy_champion = ?
            GROUP BY champion
            HAVING games >= ?
            ORDER BY (CAST(wins AS FLOAT) / games) DESC
            """,
            (lane, enemy_champion, min_games),
        ).fetchall()

    return [
        {
            "champion": row["champion"],
            "games": row["games"],
            "wins": row["wins"],
            "win_rate": round(row["wins"] / row["games"] * 100, 1),
        }
        for row in rows
    ]
