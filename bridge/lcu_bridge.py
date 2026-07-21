"""롤 클라이언트(LCU)에서 밴픽 진행 상황을 읽어서 배포된 밴픽 도우미 백엔드로
실시간 전송하는 로컬 브리지.

PC방/집 PC에서 롤 클라이언트를 켜둔 상태로 이 스크립트를 실행하면,
챔피언 선택 화면에서 벌어지는 밴/픽이 웹 페이지에 자동으로 반영된다.

사용법:
    pip install -r requirements.txt
    python lcu_bridge.py
    (필요하면) BACKEND_URL=https://내주소 python lcu_bridge.py

동작 원리:
    롤 클라이언트는 실행 중일 때 로컬에 비공식 관리용 API(LCU API)를 띄우고,
    설치 폴더의 lockfile에 접속 포트/비밀번호를 적어둔다. 이 스크립트는 그 lockfile을
    읽어서 챔피언 선택 세션(/lol-champ-select/v1/session)을 주기적으로 조회하고,
    변화가 있으면 우리 백엔드(/api/live/push)로 그대로 전달한다.
"""

import os
import time

import psutil
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BACKEND_URL = os.environ.get("BACKEND_URL", "https://backend-production-a9fe.up.railway.app")
POLL_INTERVAL = 1.0

# LCU가 쓰는 assignedPosition 값 -> 우리 백엔드의 라인 이름
POSITION_MAP = {
    "top": "TOP",
    "jungle": "JUNGLE",
    "middle": "MIDDLE",
    "bottom": "BOTTOM",
    "utility": "UTILITY",
}

# assignedPosition이 비어있을 때(상대팀은 이 필드가 안 들어오는 경우가 있음) 쓰는
# 순서 기반 대체값. LCU가 myTeam/theirTeam 배열을 보통 역할 순서대로 내려주기 때문에
# 배열 인덱스로 라인을 추정한다.
FALLBACK_LANE_ORDER = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]

# 리그 오브 레전드 클라이언트로 흔히 잡히는 프로세스 이름들 (환경에 따라 다를 수 있어서 넉넉히 잡는다)
LEAGUE_PROCESS_NAME_HINTS = ("leagueclientux", "leagueclient")

# psutil로 프로세스의 cwd를 못 읽는 환경(권한 문제 등)을 대비한 기본 설치 경로 후보
FALLBACK_LOCKFILE_PATHS = [
    r"C:\Riot Games\League of Legends\lockfile",
    os.path.expandvars(r"%LOCALAPPDATA%\Riot Games\League of Legends\lockfile"),
]


def find_lockfile() -> str | None:
    """실행 중인 League 클라이언트 프로세스의 작업 폴더에서 lockfile을 찾는다.
    cwd를 못 읽는 환경(권한 문제)에 대비해 흔한 설치 경로도 같이 확인한다."""
    matched_processes = 0
    access_denied = 0
    for proc in psutil.process_iter(["name", "exe", "cwd"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if any(hint in name for hint in LEAGUE_PROCESS_NAME_HINTS):
                matched_processes += 1
                cwd = proc.info.get("cwd")
                if cwd:
                    candidate = os.path.join(cwd, "lockfile")
                    if os.path.exists(candidate):
                        return candidate
        except psutil.AccessDenied:
            access_denied += 1
            continue
        except psutil.NoSuchProcess:
            continue

    for candidate in FALLBACK_LOCKFILE_PATHS:
        if os.path.exists(candidate):
            return candidate

    if matched_processes or access_denied:
        print(
            f"(진단) 롤 관련 프로세스 {matched_processes}개 발견, "
            f"접근 거부 {access_denied}건 — lockfile을 찾지 못했습니다."
        )
    return None


def read_lockfile(path: str):
    with open(path, encoding="utf-8") as f:
        _name, _pid, port, password, protocol = f.read().strip().split(":")
    return port, password, protocol


def fetch_champion_id_map() -> dict[int, str]:
    """Data Dragon에서 champion.json을 받아 numeric id -> 영문 key 매핑을 만든다."""
    versions = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=10).json()
    latest = versions[0]
    data = requests.get(
        f"https://ddragon.leagueoflegends.com/cdn/{latest}/data/en_US/champion.json", timeout=10
    ).json()
    return {int(v["key"]): v["id"] for v in data["data"].values()}


def _lane_fallback_by_cell(team: list[dict]) -> dict[int, str]:
    """assignedPosition이 비어있는 경우를 위한 순서 기반 라인 추정.
    LCU가 팀 배열을 보통 역할 순서(top/jungle/mid/bot/support)대로 내려주는 걸 이용한다."""
    return {p["cellId"]: FALLBACK_LANE_ORDER[i] for i, p in enumerate(team) if i < len(FALLBACK_LANE_ORDER)}


def build_actions(session: dict, champ_id_map: dict[int, str]) -> list[dict]:
    my_team = session.get("myTeam", [])
    their_team = session.get("theirTeam", [])
    my_cells = {p["cellId"]: p for p in my_team}
    their_cells = {p["cellId"]: p for p in their_team}
    fallback_lanes = {**_lane_fallback_by_cell(my_team), **_lane_fallback_by_cell(their_team)}

    flat_actions = [a for group in session.get("actions", []) for a in group]
    flat_actions.sort(key=lambda a: a["id"])

    result = []
    for a in flat_actions:
        if a["type"] not in ("ban", "pick") or not a["completed"]:
            continue

        cell_id = a["actorCellId"]
        team = "blue" if cell_id in my_cells else "red"
        champion_id = a["championId"]

        if champion_id == 0:
            if a["type"] == "ban":
                result.append({"type": "skip", "team": team})
            continue

        champion = champ_id_map.get(champion_id)
        if not champion:
            continue

        if a["type"] == "ban":
            result.append({"type": "ban", "team": team, "champion": champion})
        else:
            player = my_cells.get(cell_id) or their_cells.get(cell_id) or {}
            lane = POSITION_MAP.get(player.get("assignedPosition", ""))
            if not lane:
                lane = fallback_lanes.get(cell_id, "TOP")
            result.append({"type": "pick", "team": team, "champion": champion, "lane": lane})

    return result


def main():
    print("챔피언 id 매핑 불러오는 중...")
    champ_id_map = fetch_champion_id_map()
    print(f"백엔드: {BACKEND_URL}")

    last_sent = None
    while True:
        lockfile = find_lockfile()
        if not lockfile:
            print("롤 클라이언트를 찾을 수 없습니다. 클라이언트를 실행한 뒤 다시 시도합니다...")
            time.sleep(3)
            continue

        port, password, protocol = read_lockfile(lockfile)
        base_url = f"{protocol}://127.0.0.1:{port}"
        auth = ("riot", password)

        print("롤 클라이언트 연결됨. 챔피언 선택 화면을 기다리는 중...")
        in_champ_select = False
        error_streak = 0
        while True:
            try:
                resp = requests.get(
                    f"{base_url}/lol-champ-select/v1/session", auth=auth, verify=False, timeout=5
                )
            except requests.RequestException as e:
                print(f"롤 클라이언트 연결이 끊겼습니다 ({e}). 다시 탐색합니다...")
                break  # 클라이언트가 꺼졌을 수 있음 -> lockfile 다시 탐색

            if resp.status_code == 404:
                if last_sent is not None:
                    print("챔피언 선택 종료. 대기 상태로 전환합니다.")
                    last_sent = None
                in_champ_select = False
                error_streak = 0
                time.sleep(POLL_INTERVAL)
                continue
            if resp.status_code != 200:
                error_streak += 1
                if error_streak in (1, 10) or error_streak % 60 == 0:
                    print(f"챔피언 선택 세션 조회 실패: HTTP {resp.status_code} - {resp.text[:200]}")
                time.sleep(POLL_INTERVAL)
                continue
            error_streak = 0

            if not in_champ_select:
                print("챔피언 선택 화면 진입 감지. 밴/픽을 추적합니다...")
                in_champ_select = True

            try:
                actions = build_actions(resp.json(), champ_id_map)
            except Exception as e:
                print(f"세션 데이터 해석 실패: {e}")
                time.sleep(POLL_INTERVAL)
                continue

            if actions != last_sent:
                try:
                    requests.post(
                        f"{BACKEND_URL}/api/live/push",
                        json={"mode": "soloq", "actions": actions},
                        timeout=5,
                    )
                    print(f"밴픽 갱신 전송: {len(actions)}개 액션")
                except requests.RequestException as e:
                    print(f"백엔드 전송 실패: {e}")
                last_sent = actions

            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
