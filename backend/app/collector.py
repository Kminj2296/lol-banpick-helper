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


def collect_summoner_ids(max_summoners: int) -> list[str]:
    ids: list[str] = []

    challenger = riot_client.get_challenger_league()
    ids.extend(entry["summonerId"] for entry in challenger.get("entries", []))

    if len(ids) < max_summoners:
        grandmaster = riot_client.get_grandmaster_league()
        ids.extend(entry["summonerId"] for entry in grandmaster.get("entries", []))

    return ids[:max_summoners]


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

    summoner_ids = collect_summoner_ids(args.max_summoners)
    print(f"수집 대상 소환사 수: {len(summoner_ids)}")

    match_ids: set[str] = set()
    for i, summoner_id in enumerate(summoner_ids, 1):
        summoner = riot_client.get_summoner_by_id(summoner_id)
        puuid = summoner["puuid"]
        ids = riot_client.get_match_ids_by_puuid(puuid, count=args.matches_per_summoner)
        match_ids.update(ids)
        print(f"[{i}/{len(summoner_ids)}] 소환사 매치 {len(ids)}개 수집, 누적 매치 {len(match_ids)}개")

    print(f"총 매치 {len(match_ids)}개 처리 시작")
    with get_conn() as conn:
        for i, match_id in enumerate(match_ids, 1):
            try:
                process_match(conn, match_id)
            except Exception as e:
                print(f"매치 {match_id} 처리 실패: {e}")
            if i % 10 == 0:
                print(f"진행률: {i}/{len(match_ids)}")

    print("완료")


if __name__ == "__main__":
    main()
