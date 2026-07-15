import time

import httpx

from .config import PLATFORM, QUEUE_RANKED_SOLO, REGION, RIOT_API_KEY

# Riot API 개인 키 기준 안전한 호출 간격 (100 req / 2min 제한보다 넉넉하게)
MIN_INTERVAL = 1.3

_last_call = 0.0


def _throttle():
    global _last_call
    elapsed = time.monotonic() - _last_call
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_call = time.monotonic()


def _get(url: str, params: dict | None = None) -> dict | list:
    if not RIOT_API_KEY:
        raise RuntimeError("RIOT_API_KEY가 설정되지 않았습니다. backend/.env를 확인하세요.")

    for attempt in range(5):
        _throttle()
        resp = httpx.get(url, params=params, headers={"X-Riot-Token": RIOT_API_KEY}, timeout=10)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "2"))
            time.sleep(retry_after + 0.5)
            continue
        resp.raise_for_status()
        return resp.json()

    raise RuntimeError(f"429 재시도 초과: {url}")


def get_challenger_league() -> dict:
    url = f"https://{PLATFORM}.api.riotgames.com/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5"
    return _get(url)


def get_grandmaster_league() -> dict:
    url = f"https://{PLATFORM}.api.riotgames.com/lol/league/v4/grandmasterleagues/by-queue/RANKED_SOLO_5x5"
    return _get(url)


def get_summoner_by_id(summoner_id: str) -> dict:
    url = f"https://{PLATFORM}.api.riotgames.com/lol/summoner/v4/summoners/{summoner_id}"
    return _get(url)


def get_match_ids_by_puuid(puuid: str, count: int = 15) -> list[str]:
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    return _get(url, params={"queue": QUEUE_RANKED_SOLO, "type": "ranked", "count": count})


def get_match_detail(match_id: str) -> dict:
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return _get(url)
