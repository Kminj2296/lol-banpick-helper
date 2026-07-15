"""
Oracle's Elixir CSV(https://oracleselixir.com/tools/downloads)를 읽어서
프로 대회 경기 데이터를 game_participants에 적재하는 스크립트.

Oracle's Elixir는 공식 API/안정적인 다운로드 URL이 없어서, 사이트에서 직접
CSV를 받은 뒤 이 스크립트에 경로를 넘겨주는 방식으로 동작한다.

사용법 (backend 디렉토리에서):
    python -m app.load_pro_data --csv ~/Downloads/2025_LoL_esports_match_data.csv --league LCK
"""

import argparse
import csv

from .db import get_conn, init_db, insert_participant

POSITION_MAP = {
    "top": "TOP",
    "jng": "JUNGLE",
    "mid": "MIDDLE",
    "bot": "BOTTOM",
    "sup": "UTILITY",
}

# Oracle's Elixir는 표시용 챔피언 이름(띄어쓰기/아포스트로피 포함)을 쓰는데,
# 우리 DB는 Riot API의 내부 챔피언 ID(championName)를 쓰기 때문에 맞춰줘야 한다.
CHAMPION_NAME_MAP = {
    "Wukong": "MonkeyKing",
    "Nunu & Willump": "Nunu",
    "Renata Glasc": "Renata",
    "Kai'Sa": "Kaisa",
    "Cho'Gath": "Chogath",
    "Kha'Zix": "Khazix",
    "Vel'Koz": "Velkoz",
    "Rek'Sai": "RekSai",
    "Bel'Veth": "Belveth",
    "K'Sante": "KSante",
    "Dr. Mundo": "DrMundo",
    "LeBlanc": "Leblanc",
    "Kog'Maw": "KogMaw",
    "Jarvan IV": "JarvanIV",
    "Lee Sin": "LeeSin",
    "Master Yi": "MasterYi",
    "Miss Fortune": "MissFortune",
    "Twisted Fate": "TwistedFate",
    "Xin Zhao": "XinZhao",
    "Tahm Kench": "TahmKench",
    "Aurelion Sol": "AurelionSol",
}


def normalize_champion(name: str) -> str:
    if name in CHAMPION_NAME_MAP:
        return CHAMPION_NAME_MAP[name]
    return name.replace(" ", "").replace("'", "").replace(".", "").replace("&", "")


def load_csv(path: str, league_filter: str | None, source_label: str):
    source = f"pro:{source_label}"
    inserted_games: set[str] = set()

    with get_conn() as conn:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                position = row.get("position", "")
                if position not in POSITION_MAP:
                    continue

                league = row.get("league", "")
                if league_filter and league.upper() != league_filter.upper():
                    continue

                game_id = row.get("gameid")
                side = row.get("side")
                champion = row.get("champion")
                result = row.get("result")
                if not (game_id and side and champion and result is not None):
                    continue

                team_key = f"{game_id}_{side}"
                insert_participant(
                    conn, game_id, source, team_key,
                    lane=POSITION_MAP[position],
                    champion=normalize_champion(champion),
                    win=bool(int(result)),
                )
                inserted_games.add(game_id)

    return inserted_games


def main():
    parser = argparse.ArgumentParser(description="Oracle's Elixir CSV 로더")
    parser.add_argument("--csv", required=True, help="Oracle's Elixir에서 받은 CSV 파일 경로")
    parser.add_argument("--league", default=None, help="특정 리그만 적재 (예: LCK). 생략하면 전체")
    parser.add_argument("--source-label", default=None, help="source 라벨 (기본값: --league 값 또는 all)")
    args = parser.parse_args()

    init_db()

    source_label = args.source_label or args.league or "all"
    games = load_csv(args.csv, args.league, source_label)
    print(f"적재 완료: {len(games)}경기 (source=pro:{source_label})")


if __name__ == "__main__":
    main()
