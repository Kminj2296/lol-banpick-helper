from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import scorer
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
            "SELECT DISTINCT champion FROM game_participants ORDER BY champion"
        ).fetchall()
    return [row["champion"] for row in rows]


@app.get("/api/sources")
def get_sources():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT source, COUNT(DISTINCT game_id) AS games FROM game_participants GROUP BY source ORDER BY source"
        ).fetchall()
    return [{"source": row["source"], "games": row["games"]} for row in rows]


@app.get("/api/recommend")
def recommend(
    lane: str = Query(..., description="TOP / JUNGLE / MIDDLE / BOTTOM / UTILITY"),
    enemy_champion: str = Query(..., description="상대 챔피언 이름 (영문, 예: Darius)"),
    min_games: int = Query(5, ge=1, description="최소 표본 게임 수"),
):
    """같은 라인 1대1 상대 기준 카운터 픽 (조합 고려 없음)."""
    lane = lane.upper()
    if lane not in LANES:
        raise HTTPException(status_code=400, detail=f"lane은 {LANES} 중 하나여야 합니다")

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT gp2.champion AS champion,
                   COUNT(*) AS games,
                   SUM(gp2.win) AS wins
            FROM game_participants gp1
            JOIN game_participants gp2
                ON gp1.game_id = gp2.game_id AND gp1.team_key != gp2.team_key
            WHERE gp1.lane = ? AND gp2.lane = ? AND gp1.champion = ?
            GROUP BY gp2.champion
            HAVING games >= ?
            ORDER BY (CAST(wins AS FLOAT) / games) DESC
            """,
            (lane, lane, enemy_champion, min_games),
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


@app.get("/api/top-champions")
def top_champions(
    min_games: int = Query(5, ge=1, description="최소 표본 게임 수"),
    sources: str | None = Query(None, description="쉼표로 구분된 source 목록 (예: soloq,pro:LCK)"),
):
    """라인 구분 없는 전체 챔피언 승률 순위 (밴 후보 추천용)."""
    src_list = sources.split(",") if sources else None
    with get_conn() as conn:
        base = scorer.base_winrates(conn, lane=None, sources=src_list)

    rows = [
        {"champion": champ, "games": games, "win_rate": round(wins / games * 100, 1)}
        for champ, (games, wins) in base.items()
        if games >= min_games
    ]
    rows.sort(key=lambda r: r["win_rate"], reverse=True)
    return rows


@app.post("/api/draft/recommend")
def draft_recommend(payload: dict = Body(...)):
    """드래프트 상태(아군/적군/밴 목록)를 받아 다음 픽 추천을 반환한다."""
    lane = str(payload.get("lane", "")).upper()
    if lane not in LANES:
        raise HTTPException(status_code=400, detail=f"lane은 {LANES} 중 하나여야 합니다")

    allies = payload.get("allies", [])
    enemies = payload.get("enemies", [])
    banned = payload.get("banned", [])
    min_games = int(payload.get("min_games", 5))
    sources = payload.get("sources") or None

    with get_conn() as conn:
        results = scorer.recommend_pick(
            conn, lane, allies, enemies, banned,
            min_games=min_games, sources=sources,
        )

    return results[:20]
