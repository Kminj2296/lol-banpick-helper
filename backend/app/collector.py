"""
챌린저/그랜드마스터 랭크 게임의 매치 데이터를 수집해서
'라인별 챔피언 vs 상대 챔피언' 승패 기록을 SQLite에 쌓는 스크립트.

사용법 (backend 디렉토리에서):
    python -m app.collector --max-summoners 30 --matches-per-summoner 10
"""

import argparse

from . import riot_client
from .config import LANES
from .db import get_conn, init_db, insert_matchup, is_match_processed, mark_match_processed


def collect_puuids(max_summoners: int) -> list[str]:
    """리그 엔트리에서 puuid를 모은다.

    Riot이 league-v4 응답에 puuid를 직접 내려주는 지역/시점이 있고,
    summonerId만 내려주고 puuid는 summoner-v4로 따로 조회해야 하는
    지역/시점도 있어서 둘 다 처리한다.
    """
    puuids: list[str] = []

    def collect_from(entries: list[dict]):
        for entry in entries:
            if len(puuids) >= max_summoners:
                return
            puuid = entry.get("puuid")
            if not puuid:
                summoner = riot_client.get_summoner_by_id(entry["summonerId"])
                puuid = summoner["puuid"]
            puuids.append(puuid)

    challenger = riot_client.get_challenger_league()
    collect_from(challenger.get("entries", []))

    if len(puuids) < max_summoners:
        grandmaster = riot_client.get_grandmaster_league()
        collect_from(grandmaster.get("entries", []))

    return puuids[:max_summoners]


def process_match(conn, match_id: str):
    if is_match_processed(conn, match_id):
        return

    detail = riot_client.get_match_detail(match_id)
    participants = detail.get("info", {}).get("participants", [])

    by_lane_team: dict[tuple[str, int], dict] = {}
    for p in participants:
        lane = p.get("teamPosition")
        if lane not in LANES:
            continue
        by_lane_team[(lane, p["teamId"])] = p

    for lane in LANES:
        team_100 = by_lane_team.get((lane, 100))
        team_200 = by_lane_team.get((lane, 200))
        if not team_100 or not team_200:
            continue

        insert_matchup(
            conn, match_id, lane,
            champion=team_100["championName"],
            enemy_champion=team_200["championName"],
            win=team_100["win"],
        )
        insert_matchup(
            conn, match_id, lane,
            champion=team_200["championName"],
            enemy_champion=team_100["championName"],
            win=team_200["win"],
        )

    mark_match_processed(conn, match_id)


def main():
    parser = argparse.ArgumentParser(description="LoL 랭크 매치 수집기")
    parser.add_argument("--max-summoners", type=int, default=20)
    parser.add_argument("--matches-per-summoner", type=int, default=10)
    args = parser.parse_args()

    init_db()

    puuids = collect_puuids(args.max_summoners)
    print(f"수집 대상 소환사 수: {len(puuids)}")

    match_ids: set[str] = set()
    for i, puuid in enumerate(puuids, 1):
        ids = riot_client.get_match_ids_by_puuid(puuid, count=args.matches_per_summoner)
        match_ids.update(ids)
        print(f"[{i}/{len(puuids)}] 소환사 매치 {len(ids)}개 수집, 누적 매치 {len(match_ids)}개")

    print(f"총 매치 {len(match_ids)}개 처리 시작")
    with get_conn() as conn:
        for i, match_id in enumerate(match_ids, 1):
            try:
                process_match(conn, match_id)
            except Exception as e:
                print(f"매치 {match_id} 처리 실패: {e}")
            if i % 10 == 0:
                conn.commit()
                print(f"진행률: {i}/{len(match_ids)}")

    print("완료")


if __name__ == "__main__":
    main()
