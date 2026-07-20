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


def ban_rates(
    conn, sources: list[str] | None = None, patches: list[str] | None = None
) -> dict[str, float]:
    """챔피언별 밴률 (전체 게임 대비 몇 %가 이 챔피언을 밴했는지). {champion: 0~1}"""
    src_sql, src_params = _source_filter_sql(sources, alias="gp")
    patch_sql, patch_params = _patch_filter_sql(patches, alias="gp")
    total_row = conn.execute(
        f"SELECT COUNT(DISTINCT game_id) AS n FROM game_participants gp WHERE 1=1{src_sql}{patch_sql}",
        [*src_params, *patch_params],
    ).fetchone()
    total_games = total_row["n"] if total_row else 0
    if not total_games:
        return {}

    ban_src_sql, ban_src_params = _source_filter_sql(sources, alias="cb")
    ban_patch_sql, ban_patch_params = _patch_filter_sql(patches, alias="cb")
    rows = conn.execute(
        f"""
        SELECT champion, COUNT(DISTINCT game_id) AS bans
        FROM champion_bans cb
        WHERE 1=1{ban_src_sql}{ban_patch_sql}
        GROUP BY champion
        """,
        [*ban_src_params, *ban_patch_params],
    ).fetchall()
    return {row["champion"]: row["bans"] / total_games for row in rows}


def damage_profiles(
    conn, sources: list[str] | None = None, patches: list[str] | None = None, min_games: int = 5
) -> dict[str, dict]:
    """챔피언별 실제 딜량의 물리/마법/고정 데미지 비율. 태그가 아니라 실측 데이터라서
    "이 챔피언은 AD다"라는 판단 없이 그대로 집계만 한다. {champion: {physical_pct, magic_pct, true_pct, games}}"""
    src_sql, src_params = _source_filter_sql(sources, alias="gp")
    patch_sql, patch_params = _patch_filter_sql(patches, alias="gp")
    rows = conn.execute(
        f"""
        SELECT champion, COUNT(*) AS games,
               SUM(physical_damage) AS physical, SUM(magic_damage) AS magic, SUM(true_damage) AS true_dmg
        FROM game_participants gp
        WHERE physical_damage IS NOT NULL{src_sql}{patch_sql}
        GROUP BY champion
        """,
        [*src_params, *patch_params],
    ).fetchall()

    result = {}
    for row in rows:
        if row["games"] < min_games:
            continue
        total = (row["physical"] or 0) + (row["magic"] or 0) + (row["true_dmg"] or 0)
        if total <= 0:
            continue
        result[row["champion"]] = {
            "physical_pct": row["physical"] / total,
            "magic_pct": row["magic"] / total,
            "true_pct": row["true_dmg"] / total,
            "games": row["games"],
        }
    return result


def cc_contribution(
    conn, sources: list[str] | None = None, patches: list[str] | None = None, min_games: int = 5
) -> dict[str, float]:
    """챔피언별 분당 CC 기여도(상대를 얼마나 오래 CC 걸었는지, 실측치). {champion: 초/분}"""
    src_sql, src_params = _source_filter_sql(sources, alias="gp")
    patch_sql, patch_params = _patch_filter_sql(patches, alias="gp")
    rows = conn.execute(
        f"""
        SELECT champion, COUNT(*) AS games,
               SUM(time_ccing_others) AS total_cc, SUM(game_duration_sec) AS total_duration
        FROM game_participants gp
        WHERE time_ccing_others IS NOT NULL AND game_duration_sec > 0{src_sql}{patch_sql}
        GROUP BY champion
        """,
        [*src_params, *patch_params],
    ).fetchall()

    result = {}
    for row in rows:
        if row["games"] < min_games or not row["total_duration"]:
            continue
        result[row["champion"]] = (row["total_cc"] or 0) / (row["total_duration"] / 60)
    return result


def power_curve(
    conn, sources: list[str] | None = None, patches: list[str] | None = None, min_bucket_games: int = 10
) -> dict[str, dict]:
    """챔피언별 게임 길이 구간(초반<20분/중반/후반>=30분)별 승률로 본 파워 커브 (실측치).
    skew = 초반 승률 - 후반 승률 (양수면 초반이 강한 챔피언). {champion: {early_wr, mid_wr, late_wr, skew, ...}}"""
    src_sql, src_params = _source_filter_sql(sources, alias="gp")
    patch_sql, patch_params = _patch_filter_sql(patches, alias="gp")
    rows = conn.execute(
        f"""
        SELECT champion,
               SUM(CASE WHEN game_duration_sec < 1200 THEN 1 ELSE 0 END) AS early_games,
               SUM(CASE WHEN game_duration_sec < 1200 THEN win ELSE 0 END) AS early_wins,
               SUM(CASE WHEN game_duration_sec >= 1200 AND game_duration_sec < 1800 THEN 1 ELSE 0 END) AS mid_games,
               SUM(CASE WHEN game_duration_sec >= 1200 AND game_duration_sec < 1800 THEN win ELSE 0 END) AS mid_wins,
               SUM(CASE WHEN game_duration_sec >= 1800 THEN 1 ELSE 0 END) AS late_games,
               SUM(CASE WHEN game_duration_sec >= 1800 THEN win ELSE 0 END) AS late_wins
        FROM game_participants gp
        WHERE game_duration_sec IS NOT NULL{src_sql}{patch_sql}
        GROUP BY champion
        """,
        [*src_params, *patch_params],
    ).fetchall()

    result = {}
    for row in rows:
        if row["early_games"] < min_bucket_games or row["late_games"] < min_bucket_games:
            continue
        early_wr = row["early_wins"] / row["early_games"]
        late_wr = row["late_wins"] / row["late_games"]
        mid_wr = row["mid_wins"] / row["mid_games"] if row["mid_games"] >= min_bucket_games else None
        result[row["champion"]] = {
            "early_wr": early_wr,
            "mid_wr": mid_wr,
            "late_wr": late_wr,
            "skew": early_wr - late_wr,
            "early_games": row["early_games"],
            "late_games": row["late_games"],
        }
    return result


def _progress_weight(known_count: int, ramp: int = 4) -> float:
    """드래프트에서 정보가 쌓일수록(known_count) 그 정보에 대한 신뢰도를 0.5~1.0으로
    올려주는 가중치. 시너지는 지금까지 나온 아군 수, 카운터는 상대 수에 따라 커진다
    (선픽처럼 아는 게 적을 때는 한두 게임 표본만으로 결론 내리지 않도록)."""
    return 0.5 + 0.5 * min(1.0, known_count / ramp)


def recommend_pick(
    conn,
    lane: str,
    allies: list[str],
    enemies: list[str],
    banned: list[str],
    min_games: int = 5,
    min_pair_games: int = 5,
    sources: list[str] | None = None,
    patches: list[str] | None = None,
    shrinkage_k: int = 10,
    base_shrinkage_k: int = 30,
    lane_fit_weight: float = 12.0,
    lane_fit_confidence_games: int = 8,
    ban_safety_weight: float = 6.0,
    draft_progress_ramp: int = 8,
    damage_diversity_weight: float = 3.0,
    cc_coverage_weight: float = 3.0,
    curve_alignment_weight: float = 3.0,
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

    픽 순서에 따른 전략 차이 (선픽 vs 후픽):
    - 시너지 보정치는 지금까지 나온 아군 수, 카운터 보정치는 상대 수가 늘어날수록
      (_progress_weight) 신뢰도를 높여서 더 크게 반영한다. 아군/상대 픽이 1~2개뿐인
      선픽 단계에서는 그 소수 표본만으로 과하게 결론 내리지 않도록 절반 가중치로
      시작해서, 픽이 쌓일수록(후픽) 최대 가중치까지 커진다.
    - ban_safety_weight: 반대로 밴 회피 보너스는 드래프트 초반(아군+상대 픽이 적을
      때)일수록 크게 반영하고, 픽이 진행될수록 0으로 줄어든다. 이미 밴 페이즈가
      끝났거나 후픽 단계라 밴당할 위험이 의미 없어졌기 때문이다. 후보 풀 평균
      밴률보다 이 챔피언 밴률이 낮으면 가산점을, 높으면 감점을 준다.

    아군 픽이 드러날수록 반영되는 팀 정렬 보정 (전부 실측 데이터 기반, 챔피언
    아키타입 같은 주관적 태그는 안 씀 — 아군이 1명도 없으면 비교 대상이 없어서 계산 안 함):
    - damage_diversity_weight: 아군의 물리/마법 데미지 비율이 한쪽으로 쏠려 있으면
      (예: 이미 픽한 챔피언들이 전부 물리 딜러) 반대 성향(마법 딜러) 챔피언에 가산점을
      줘서 상대가 방어 아이템 하나로 팀 전체를 카운터하기 어렵게 만든다.
    - cc_coverage_weight: 아군의 분당 CC 기여도가 낮으면(=아직 CC가 부족한 조합) CC를
      많이 주는 챔피언에 가산점을 준다. 이미 CC가 충분하면 추가 보너스는 없다.
    - curve_alignment_weight: 아군의 초반/후반 승률 격차(skew)와 이 챔피언의 skew가
      같은 방향이면(둘 다 초반형이거나 둘 다 후반형) 가산점을 준다. 팀 전체가 같은
      타이밍에 강해야 한다는 걸 승률 데이터로 확인한 것.
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
    ban_rate_data = ban_rates(conn, sources, patches)

    synergy_weight = _progress_weight(len(allies), draft_progress_ramp)
    counter_weight = _progress_weight(len(enemies), draft_progress_ramp)

    known_picks = len(allies) + len(enemies)
    early_weight = max(0.0, 1.0 - known_picks / draft_progress_ramp)
    candidate_ban_rates = [ban_rate_data.get(c, 0.0) for c in candidates]
    avg_ban_rate = sum(candidate_ban_rates) / len(candidate_ban_rates) if candidate_ban_rates else 0.0

    # 아군 팀 정렬 보정용 실측 데이터 (아군이 있을 때만 계산할 가치가 있음)
    team_damage_skew = team_cc_per_min = team_curve_skew = None
    if allies:
        dmg_data = damage_profiles(conn, sources, patches)
        cc_data = cc_contribution(conn, sources, patches)
        curve_data = power_curve(conn, sources, patches)

        ally_dmg = [dmg_data[a] for a in allies if a in dmg_data]
        if ally_dmg:
            team_damage_skew = (
                sum(d["physical_pct"] - d["magic_pct"] for d in ally_dmg) / len(ally_dmg)
            )

        ally_cc = [cc_data[a] for a in allies if a in cc_data]
        if ally_cc:
            team_cc_per_min = sum(ally_cc) / len(ally_cc)
        cc_pool = list(cc_data.values())
        pool_avg_cc = sum(cc_pool) / len(cc_pool) if cc_pool else None

        ally_curve = [curve_data[a]["skew"] for a in allies if a in curve_data]
        if ally_curve:
            team_curve_skew = sum(ally_curve) / len(ally_curve)
    else:
        dmg_data = cc_data = curve_data = {}
        pool_avg_cc = None

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
                weight = (s_games / (s_games + shrinkage_k)) * synergy_weight
                components.append({
                    "type": "synergy",
                    "with": ally,
                    "games": s_games,
                    "win_rate": round(s_wr * 100, 1),
                    "delta": round((s_wr - b_wr) * 100 * synergy_weight, 1),
                    "applied_delta": (s_wr - b_wr) * weight,
                })

        for enemy, cmap in counter_maps:
            if champ in cmap and cmap[champ][0] >= min_pair_games:
                c_games, c_wins = cmap[champ]
                c_wr = c_wins / c_games
                weight = (c_games / (c_games + shrinkage_k)) * counter_weight
                components.append({
                    "type": "counter",
                    "vs": enemy,
                    "games": c_games,
                    "win_rate": round(c_wr * 100, 1),
                    "delta": round((c_wr - b_wr) * 100 * counter_weight, 1),
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

        if early_weight > 0 and champ in ban_rate_data:
            this_ban_rate = ban_rate_data.get(champ, 0.0)
            ban_safety_pp = early_weight * ban_safety_weight * (avg_ban_rate - this_ban_rate) * 100
            if abs(ban_safety_pp) >= 0.1:
                components.append({
                    "type": "ban_safety",
                    "ban_rate": round(this_ban_rate * 100, 1),
                    "delta": round(ban_safety_pp, 1),
                    "applied_delta": early_weight * ban_safety_weight * (avg_ban_rate - this_ban_rate),
                })

        if team_damage_skew is not None and champ in dmg_data:
            cand_skew = dmg_data[champ]["physical_pct"] - dmg_data[champ]["magic_pct"]
            diversity_raw = max(-1.0, min(1.0, -(team_damage_skew * cand_skew) * 4))
            diversity_pp = damage_diversity_weight * diversity_raw
            if abs(diversity_pp) >= 0.1:
                components.append({
                    "type": "damage_diversity",
                    "delta": round(diversity_pp, 1),
                    "applied_delta": diversity_pp / 100,
                })

        if team_cc_per_min is not None and pool_avg_cc and champ in cc_data:
            need = max(0.0, 1.0 - team_cc_per_min / pool_avg_cc)
            cand_relative = (cc_data[champ] - pool_avg_cc) / pool_avg_cc
            cc_pp = cc_coverage_weight * need * cand_relative
            if abs(cc_pp) >= 0.1:
                components.append({
                    "type": "cc_coverage",
                    "delta": round(cc_pp, 1),
                    "applied_delta": cc_pp / 100,
                })

        if team_curve_skew is not None and champ in curve_data:
            cand_skew = curve_data[champ]["skew"]
            curve_raw = max(-1.0, min(1.0, (team_curve_skew * cand_skew) * 8))
            curve_pp = curve_alignment_weight * curve_raw
            if abs(curve_pp) >= 0.1:
                components.append({
                    "type": "curve_alignment",
                    "delta": round(curve_pp, 1),
                    "applied_delta": curve_pp / 100,
                })

        total_delta = sum(comp.pop("applied_delta") for comp in components)
        estimated = max(0.0, min(1.0, b_wr + total_delta))

        results.append({
            "champion": champ,
            "base_games": b_games,
            "base_win_rate": round(b_wr * 100, 1),
            "estimated_win_rate": round(estimated * 100, 1),
            "ban_rate": round(ban_rate_data.get(champ, 0.0) * 100, 1),
            "components": sorted(components, key=lambda c: abs(c["delta"]), reverse=True),
        })

    results.sort(key=lambda r: r["estimated_win_rate"], reverse=True)
    return results
