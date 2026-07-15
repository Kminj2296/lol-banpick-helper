"""
드래프트 추천 점수 계산.

지금은 '개별 챔피언 승률 + 같은 팀 챔피언과의 시너지 보정치 + 상대 챔피언과의
카운터 보정치'를 더하는 가법 모델이다. 표본이 적은 상태에서도 그럭저럭
해석 가능한 추정치를 낼 수 있는 방식이라 우선 이걸로 시작한다.

나중에 로지스틱 회귀/머신러닝 모델로 바꾸더라도 recommend_pick()의
반환 형태(챔피언별 estimated_win_rate + 근거 components)는 그대로 유지하고
내부 계산만 교체하면 되도록 분리해뒀다.
"""


def _source_filter_sql(sources: list[str] | None, alias: str = "gp") -> tuple[str, list]:
    if not sources:
        return "", []
    placeholders = ",".join("?" for _ in sources)
    return f" AND {alias}.source IN ({placeholders})", list(sources)


def base_winrates(conn, lane: str | None = None, sources: list[str] | None = None) -> dict[str, tuple[int, int]]:
    """라인(옵션)별 챔피언 표본 수/승수. {champion: (games, wins)}"""
    where = "WHERE 1=1"
    params: list = []
    if lane:
        where += " AND gp.lane = ?"
        params.append(lane)
    src_sql, src_params = _source_filter_sql(sources)
    where += src_sql
    params += src_params

    rows = conn.execute(
        f"""
        SELECT champion, COUNT(*) AS games, SUM(win) AS wins
        FROM game_participants gp
        {where}
        GROUP BY champion
        """,
        params,
    ).fetchall()
    return {row["champion"]: (row["games"], row["wins"]) for row in rows}


def synergy_pairs(conn, with_champion: str, sources: list[str] | None = None) -> dict[str, tuple[int, int]]:
    """with_champion과 같은 팀일 때 각 챔피언의 표본 수/승수."""
    src_sql, src_params = _source_filter_sql(sources, alias="gp2")
    rows = conn.execute(
        f"""
        SELECT gp2.champion AS champion, COUNT(*) AS games, SUM(gp2.win) AS wins
        FROM game_participants gp1
        JOIN game_participants gp2
            ON gp1.team_key = gp2.team_key AND gp1.champion != gp2.champion
        WHERE gp1.champion = ?{src_sql}
        GROUP BY gp2.champion
        """,
        [with_champion, *src_params],
    ).fetchall()
    return {row["champion"]: (row["games"], row["wins"]) for row in rows}


def counter_pairs(conn, vs_champion: str, sources: list[str] | None = None) -> dict[str, tuple[int, int]]:
    """vs_champion이 상대팀일 때 각 챔피언의 표본 수/승수."""
    src_sql, src_params = _source_filter_sql(sources, alias="gp2")
    rows = conn.execute(
        f"""
        SELECT gp2.champion AS champion, COUNT(*) AS games, SUM(gp2.win) AS wins
        FROM game_participants gp1
        JOIN game_participants gp2
            ON gp1.game_id = gp2.game_id AND gp1.team_key != gp2.team_key
        WHERE gp1.champion = ?{src_sql}
        GROUP BY gp2.champion
        """,
        [vs_champion, *src_params],
    ).fetchall()
    return {row["champion"]: (row["games"], row["wins"]) for row in rows}


def recommend_pick(
    conn,
    lane: str,
    allies: list[str],
    enemies: list[str],
    banned: list[str],
    min_games: int = 5,
    min_pair_games: int = 2,
    sources: list[str] | None = None,
    shrinkage_k: int = 10,
) -> list[dict]:
    """
    shrinkage_k: 표본이 적은 시너지/카운터 보정치를 얼마나 축소할지 결정하는 값.
    games/(games+shrinkage_k)를 가중치로 곱해서, 표본이 적을수록(예: 2게임 100%
    승률) 보정치가 그대로 반영되지 않고 0에 가깝게 줄어들도록 한다.
    """
    base = base_winrates(conn, lane=lane, sources=sources)
    excluded = set(allies) | set(enemies) | set(banned)
    candidates = {c: v for c, v in base.items() if c not in excluded and v[0] >= min_games}

    synergy_maps = [(ally, synergy_pairs(conn, ally, sources)) for ally in allies]
    counter_maps = [(enemy, counter_pairs(conn, enemy, sources)) for enemy in enemies]

    results = []
    for champ, (b_games, b_wins) in candidates.items():
        b_wr = b_wins / b_games
        components = []

        for ally, smap in synergy_maps:
            if champ in smap and smap[champ][0] >= min_pair_games:
                s_games, s_wins = smap[champ]
                s_wr = s_wins / s_games
                weight = s_games / (s_games + shrinkage_k)
                components.append({
                    "type": "synergy",
                    "with": ally,
                    "games": s_games,
                    "win_rate": round(s_wr * 100, 1),
                    "delta": round((s_wr - b_wr) * 100, 1),
                    "applied_delta": (s_wr - b_wr) * weight,
                })

        for enemy, cmap in counter_maps:
            if champ in cmap and cmap[champ][0] >= min_pair_games:
                c_games, c_wins = cmap[champ]
                c_wr = c_wins / c_games
                weight = c_games / (c_games + shrinkage_k)
                components.append({
                    "type": "counter",
                    "vs": enemy,
                    "games": c_games,
                    "win_rate": round(c_wr * 100, 1),
                    "delta": round((c_wr - b_wr) * 100, 1),
                    "applied_delta": (c_wr - b_wr) * weight,
                })

        total_delta = sum(comp.pop("applied_delta") for comp in components)
        estimated = max(0.0, min(1.0, b_wr + total_delta))

        results.append({
            "champion": champ,
            "base_games": b_games,
            "base_win_rate": round(b_wr * 100, 1),
            "estimated_win_rate": round(estimated * 100, 1),
            "components": sorted(components, key=lambda c: abs(c["delta"]), reverse=True),
        })

    results.sort(key=lambda r: r["estimated_win_rate"], reverse=True)
    return results
