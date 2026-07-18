import json
import os

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import scorer
from .config import LANES
from .db import get_conn, init_db
from .live import hub

app = FastAPI(title="LoL Ban/Pick Helper API")

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
with open(os.path.join(_DATA_DIR, "champion_names_ko.json"), encoding="utf-8") as f:
    CHAMPION_NAMES_KO: dict[str, str] = json.load(f)
with open(os.path.join(_DATA_DIR, "champion_images.json"), encoding="utf-8") as f:
    CHAMPION_IMAGES: dict[str, str] = json.load(f)

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


@app.get("/api/champion-names")
def get_champion_names():
    """챔피언 영문 ID -> 한국어 이름 매핑 (Riot Data Dragon 기준)."""
    return CHAMPION_NAMES_KO


@app.get("/api/champion-images")
def get_champion_images():
    """챔피언 영문 ID -> 썸네일 이미지 URL 매핑 (Riot Data Dragon CDN)."""
    return CHAMPION_IMAGES


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
    lane: str | None = Query(None, description="TOP / JUNGLE / MIDDLE / BOTTOM / UTILITY (생략 시 전체 라인 통합)"),
    sources: str | None = Query(None, description="쉼표로 구분된 source 목록 (예: soloq,pro:LCK)"),
):
    """챔피언 승률 순위 (밴 후보 추천용). lane을 지정하면 해당 라인만 집계."""
    if lane:
        lane = lane.upper()
        if lane not in LANES:
            raise HTTPException(status_code=400, detail=f"lane은 {LANES} 중 하나여야 합니다")

    src_list = sources.split(",") if sources else None
    with get_conn() as conn:
        base = scorer.base_winrates(conn, lane=lane, sources=src_list)

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


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """PC방 로컬 브리지가 보내는 실시간 밴픽 상태를 받아보는 프론트엔드용 소켓."""
    await hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(websocket)


@app.post("/api/live/push")
async def live_push(payload: dict = Body(...)):
    """PC방 로컬 브리지(lcu_bridge.py)가 롤 클라이언트에서 읽은 밴픽 상태를 보내는 엔드포인트."""
    await hub.push(payload)
    return {"ok": True}


_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
