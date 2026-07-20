"""
챌린저/그랜드마스터 랭크 게임의 매치 데이터를 수집해서
경기당 10명 전원의 팀/라인/챔피언/승패를 SQLite에 쌓는 스크립트.
(같은 팀 챔피언 시너지, 상대 챔피언 카운터 계산에 필요)

사용법 (backend 디렉토리에서):
    python -m app.collector --max-summoners 30 --matches-per-summoner 10
"""

import argparse

import httpx

from . import riot_client
from .config import LANES
from .db import get_conn, init_db, insert_ban, insert_participant, is_match_processed, mark_match_processed

SOURCE = "soloq"


def fetch_champion_id_map() -> dict[int, str]:
    """Data Dragon에서 champion.json을 받아 numeric id -> 영문 key 매핑을 만든다.
    밴 데이터(info.teams[].bans)는 championId만 주고 championName은 안 줘서 필요하다."""
    versions = httpx.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=10).json()
    latest = versions[0]
    data = httpx.get(
        f"https://ddragon.leagueoflegends.com/cdn/{latest}/data/en_US/champion.json", timeout=10
    ).json()
    return {int(v["key"]): v["id"] for v in data["data"].values()}


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


def extract_patch(game_version: str) -> str | None:
    """'14.13.587.1234' 같은 gameVersion에서 'major.minor'만 뽑아 패치 버전으로 쓴다."""
    parts = game_version.split(".")
    if len(parts) < 2:
        return None
    return f"{parts[0]}.{parts[1]}"


def process_match(conn, match_id: str, champ_id_map: dict[int, str]):
    if is_match_processed(conn, match_id):
        return

    detail = riot_client.get_match_detail(match_id)
    info = detail.get("info", {})
    patch = extract_patch(info.get("gameVersion", ""))
    game_duration_sec = info.get("gameDuration")
    participants = info.get("participants", [])

    for p in participants:
        lane = p.get("teamPosition")
        if lane not in LANES:
            continue

        team_key = f"{match_id}_{p['teamId']}"
        insert_participant(
            conn, match_id, SOURCE, team_key,
            lane=lane,
            champion=p["championName"],
            win=p["win"],
            patch=patch,
            physical_damage=p.get("physicalDamageDealtToChampions"),
            magic_damage=p.get("magicDamageDealtToChampions"),
            true_damage=p.get("trueDamageDealtToChampions"),
            time_ccing_others=p.get("timeCCingOthers"),
            game_duration_sec=game_duration_sec,
        )

    for team in info.get("teams", []):
        for ban in team.get("bans", []):
            champion_id = ban.get("championId", -1)
            if champion_id <= 0:
                continue
            champion = champ_id_map.get(champion_id)
            if champion:
                insert_ban(conn, match_id, SOURCE, champion, patch=patch)

    mark_match_processed(conn, match_id)


def main():
    parser = argparse.ArgumentParser(description="LoL 랭크 매치 수집기")
    parser.add_argument("--max-summoners", type=int, default=20)
    parser.add_argument("--matches-per-summoner", type=int, default=10)
    args = parser.parse_args()

    init_db()

    print("챔피언 id 매핑 불러오는 중...")
    champ_id_map = fetch_champion_id_map()

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
                process_match(conn, match_id, champ_id_map)
            except Exception as e:
                print(f"매치 {match_id} 처리 실패: {e}")
            if i % 10 == 0:
                conn.commit()
                print(f"진행률: {i}/{len(match_ids)}")

    print("완료")


if __name__ == "__main__":
    main()
