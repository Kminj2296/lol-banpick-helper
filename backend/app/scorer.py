"""
드래프트 추천 점수 계산.

지금은 '개별 챔피언 승률 + 같은 팀 챔피언과의 시너지 보정치 + 상대 챔피언과의
카운터 보정치'를 더하는 가법 모델이다. 표본이 적은 상태에서도 그럭저럭
해석 가능한 추정치를 낼 수 있는 방식이라 우선 이걸로 시작한다.

나중에 로지스틱 회귀/머신러닝 모델로 바꾸더라도 recommend_pick()의
반환 형태(챔피언별 estimated_win_rate + 근거 components)는 그대로 유지하고
내부 계산만 교체하면 되도록 분리해뒀다.
"""


def shrink_win_rate(wins: int, games: int, prior: float, k: int) -> float:
    """표본이 적을수록(games가 작을수록) prior 쪽으로 끌어당긴 승률.
    games/(games+k)를 신뢰 가중치로 써서, 표본이 아주 적으면 거의 prior에 가깝게,
    표본이 충분히 많으면 원래 관측 승률에 가깝게 수렴한다."""
    wr = wins / games
    weight = games / (games + k)
    return wr * weight + prior * (1 - weight)


def _source_filter_sql(sources: list[str] | None, alias: str = "gp") -> tuple[str, list]:
    if not sources:
        return "", []
    placeholders = ",".join("?" for _ in sources)
    return f" AND {alias}.source IN ({placeholders})", list(sources)


def _patch_filter_sql(patches: list[str] | None, alias: str = "gp") -> tuple[str, list]:
    if not patches:
        return "", []
    placeholders = ",".join("?" for _ in patches)
    return f" AND {alias}.patch IN ({placeholders})", list(patches)


def list_patches(conn, sources: list[str] | None = None) -> list[dict]:
    """수집된 패치 버전별 게임 수 (최신 패치가 먼저 오도록 정렬). 패치 정보가 없는
    예전 데이터는 patch가 NULL이라 여기 안 잡힌다."""
    src_sql, src_params = _source_filter_sql(sources)
    rows = conn.execute(
        f"""
        SELECT patch, COUNT(DISTINCT game_id) AS games
        FROM game_participants gp
        WHERE patch IS NOT NULL{src_sql}
        GROUP BY patch
        """,
        src_params,
    ).fetchall()

    def _sort_key(patch: str):
        return tuple(int(x) if x.isdigit() else 0 for x in patch.split("."))

    return sorted(
        [{"patch": row["patch"], "games": row["games"]} for row in rows],
        key=lambda r: _sort_key(r["patch"]),
        reverse=True,
    )


def base_winrates(
    conn, lane: str | None = None, sources: list[str] | None = None, patches: list[str] | None = None
) -> dict[str, tuple[int, int]]:
    """라인(옵션)별 챔피언 표본 수/승수. {champion: (games, wins)}"""
    where = "WHERE 1=1"
    params: list = []
    if lane:
        where += " AND gp.lane = ?"
        params.append(lane)
    src_sql, src_params = _source_filter_sql(sources)
    where += src_sql
    params += src_params
    patch_sql, patch_params = _patch_filter_sql(patches)
    where += patch_sql
    params += patch_params

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


def synergy_pairs(
    conn, with_champion: str, sources: list[str] | None = None, patches: list[str] | None = None
) -> dict[str, tuple[int, int]]:
    """with_champion과 같은 팀일 때 각 챔피언의 표본 수/승수."""
    src_sql, src_params = _source_filter_sql(sources, alias="gp2")
    patch_sql, patch_params = _patch_filter_sql(patches, alias="gp2")
    rows = conn.execute(
        f"""
        SELECT gp2.champion AS champion, COUNT(*) AS games, SUM(gp2.win) AS wins
        FROM game_participants gp1
        JOIN game_participants gp2
            ON gp1.team_key = gp2.team_key AND gp1.champion != gp2.champion
        WHERE gp1.champion = ?{src_sql}{patch_sql}
        GROUP BY gp2.champion
        """,
        [with_champion, *src_params, *patch_params],
    ).fetchall()
    return {row["champion"]: (row["games"], row["wins"]) for row in rows}


def counter_pairs(
    conn, vs_champion: str, sources: list[str] | None = None, patches: list[str] | None = None
) -> dict[str, tuple[int, int]]:
    """vs_champion이 상대팀일 때 각 챔피언의 표본 수/승수."""
    src_sql, src_params = _source_filter_sql(sources, alias="gp2")
    patch_sql, patch_params = _patch_filter_sql(patches, alias="gp2")
    rows = conn.execute(
        f"""
        SELECT gp2.champion AS champion, COUNT(*) AS games, SUM(gp2.win) AS wins
        FROM game_participants gp1
        JOIN game_participants gp2
            ON gp1.game_id = gp2.game_id AND gp1.team_key != gp2.team_key
        WHERE gp1.champion = ?{src_sql}{patch_sql}
        GROUP BY gp2.champion
        """,
        [vs_champion, *src_params, *patch_params],
    ).fetchall()
    return {row["champion"]: (row["games"], row["wins"]) for row in rows}


def lane_shares(
    conn, sources: list[str] | None = None, patches: list[str] | None = None
) -> dict[str, dict]:
    """
    챔피언별로 전체 게임(모든 라인 통틀어) 대비 각 라인에서 픽된 비율.
    {champion: {"total": 전체게임수, "shares": {lane: 비율}}}

    표본이 적으면 우연히 특정 라인에서만 목격된 챔피언(예: 서포터가 탑 3게임
    autofill로 이겼을 뿐인 경우)도 그 라인 후보로 섞여 들어오는데, 이걸
    "실제로 이 라인에서 자주 픽되는가"로 걸러내기 위한 보조 지표다.
    """
    src_sql, src_params = _source_filter_sql(sources)
    patch_sql, patch_params = _patch_filter_sql(patches)
    rows = conn.execute(
        f"""
        SELECT champion, lane, COUNT(*) AS games
        FROM game_participants gp
        WHERE 1=1{src_sql}{patch_sql}
        GROUP BY champion, lane
        """,
        [*src_params, *patch_params],
    ).fetchall()

    totals: dict[str, int] = {}
    per_lane: dict[str, dict[str, int]] = {}
    for row in rows:
        champ, lane, games = row["champion"], row["lane"], row["games"]
        totals[champ] = totals.get(champ, 0) + games
        per_lane.setdefault(champ, {})[lane] = games

    return {
        champ: {
            "total": totals[champ],
            "shares": {lane: games / totals[champ] for lane, games in lanes.items()},
        }
        for champ, lanes in per_lane.items()
    }


def recommend_pick(
    conn,
    lane: str,
    allies: list[str],
    enemies: list[str],
    banned: list[str],
    min_games: int = 5,
    min_pair_games: int = 2,
    sources: list[str] | None = None,
    patches: list[str] | None = None,
    shrinkage_k: int = 10,
    base_shrinkage_k: int = 30,
    lane_fit_weight: float = 12.0,
    lane_fit_confidence_games: int = 8,
) -> list[dict]:
    """
    shrinkage_k: 표본이 적은 시너지/카운터 보정치를 얼마나 축소할지 결정하는 값.
    games/(games+shrinkage_k)를 가중치로 곱해서, 표본이 적을수록(예: 2게임 100%
    승률) 보정치가 그대로 반영되지 않고 0에 가깝게 줄어들도록 한다.

    base_shrinkage_k: 챔피언 단독 승률(기본 승률) 자체도 표본이 적으면(예: 13게임
    76.9%) 이 라인 전체 평균 승률 쪽으로 끌어당겨서, "표본이 적어서 우연히 승률이
    튄" 챔피언이 추천 1위로 올라오는 걸 막는다. 화면에 보이는 "기본 승률"은 원래
    관측값 그대로 두고, 순위 계산에 쓰는 값만 보정한다 (근거에 "표본 보정"으로 표시).

    lane_fit_weight: 이 챔피언이 요청한 라인에서 픽되는 비율(lane_shares)에
    곱해서 더하는 최대 가산점(%p). 예를 들어 어떤 챔피언이 전체 게임의 100%를
    이 라인에서 뛰었으면 +lane_fit_weight%p, 10%만 이 라인이었으면 소폭만 더한다.
    lane_fit_confidence_games보다 총 표본이 적으면 그 비율만큼 가산점을 축소한다.
    """
    base = base_winrates(conn, lane=lane, sources=sources, patches=patches)
    excluded = set(allies) | set(enemies) | set(banned)
    candidates = {c: v for c, v in base.items() if c not in excluded and v[0] >= min_games}

    total_games = sum(g for g, _ in base.values())
    total_wins = sum(w for _, w in base.values())
    lane_prior = (total_wins / total_games) if total_games else 0.5

    synergy_maps = [(ally, synergy_pairs(conn, ally, sources, patches)) for ally in allies]
    counter_maps = [(enemy, counter_pairs(conn, enemy, sources, patches)) for enemy in enemies]
    lane_share_data = lane_shares(conn, sources, patches)

    results = []
    for champ, (b_games, b_wins) in candidates.items():
        b_wr = b_wins / b_games
        components = []

        adjusted_base_wr = shrink_win_rate(b_wins, b_games, lane_prior, base_shrinkage_k)
        sample_adjust_pp = (adjusted_base_wr - b_wr) * 100
        if abs(sample_adjust_pp) >= 0.1:
            components.append({
                "type": "sample_adjust",
                "games": b_games,
                "lane_avg": round(lane_prior * 100, 1),
                "delta": round(sample_adjust_pp, 1),
                "applied_delta": adjusted_base_wr - b_wr,
            })

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

        info = lane_share_data.get(champ)
        if info:
            share = info["shares"].get(lane, 0.0)
            confidence = min(1.0, info["total"] / lane_fit_confidence_games)
            lane_fit_pp = share * lane_fit_weight * confidence
            if lane_fit_pp >= 0.1:
                components.append({
                    "type": "lane_fit",
                    "lane_share": round(share * 100, 1),
                    "games": info["total"],
                    "delta": round(lane_fit_pp, 1),
                    "applied_delta": lane_fit_pp / 100,
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
