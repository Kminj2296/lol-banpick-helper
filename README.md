# 롤 밴픽 도우미

**배포 링크**: https://backend-production-a9fe.up.railway.app

밴픽 순서(솔로랭크 방식/대회 방식 선택 가능)를 따라가면서, 픽 차례마다 지금까지의 아군/적군
조합을 고려해 승률이 높은 챔피언을 추천해주는 웹앱입니다. 챔피언은 한글/영문 아무거나 검색할 수
있습니다. 라인 1대1 카운터 픽 검색 기능도 별도로 있습니다.

lol.ps 같은 스크래핑 사이트 대신, **Riot 공식 API로 챌린저/그랜드마스터 랭크 게임 데이터를 직접 수집**해서
경기당 10명 전원의 팀/라인/챔피언/승패를 자체 집계합니다. Oracle's Elixir CSV를 통해 LCK 등 프로 대회
데이터도 추가로 넣을 수 있습니다.

## 승률 계산 방식

정확히 같은 10챔피언 조합이 다시 나올 확률은 사실상 0이라, "이 조합의 승률"을 직접 셀 수는 없습니다.
대신 다음을 더하는 **가법(additive) 모델**을 씁니다:

```
추정 승률 = 개별 챔피언 기본 승률
          + Σ (같은 팀 챔피언과 함께일 때 승률 - 기본 승률) × 시너지 가중치(t)  ← 시너지
          + Σ (상대 챔피언과 맞붙을 때 승률 - 기본 승률) × 카운터 가중치(t)     ← 카운터
          + 라인 적합도 보정                                                ← 이 라인에서 실제로 얼마나 자주 픽되는지
          + 밴 회피 보정 × 선픽 가중치(t)                                    ← 밴될 확률이 낮을수록 가산점 (선픽일수록 크게)
```

표본이 적은 매치업(예: 2게임 100%)이 그대로 반영되지 않도록, 표본 수에 비례해 보정치를 줄이는
축소(shrinkage) 가중치를 곱합니다 (`app/scorer.py`의 `shrinkage_k`).

라인 적합도는 그 챔피언의 전체 게임(모든 라인 통틀어) 중 몇 %가 지금 요청한 라인에서
나왔는지를 보고 가산점을 줍니다. 특정 라인에서 표본 수 자체는 `min_games`를 넘겨도
전체로 보면 다른 라인/역할로 훨씬 자주 픽되는 챔피언(예: 서포터가 어쩌다 탑에서 이긴 경우)이
상위에 뜨는 걸 줄이기 위한 보정입니다 (`app/scorer.py`의 `lane_fit_weight`,
`lane_fit_confidence_games`).

**기본 승률 자체도 표본이 적으면(예: 13게임 76.9%) 이 라인 전체 평균 승률 쪽으로 끌어당겨서
보정합니다** (`app/scorer.py`의 `shrink_win_rate`, `base_shrinkage_k`). 화면에 보이는
"기본 승률"은 원본 관측값 그대로 두고, 추정 승률/순위 계산에만 보정된 값을 쓰며 "표본 보정"
근거로 그 차이를 보여줍니다. 표본이 극히 적은 챔피언이 우연한 승률로 추천 최상단에 뜨는 걸
막기 위한 장치입니다.

**패치 필터링**: 매치 데이터는 수집 시점의 패치 버전(`patch` 컬럼, 예 "14.13")을 함께 저장합니다.
`/api/patches`로 수집된 패치 목록을 볼 수 있고, `/api/top-champions`·`/api/draft/recommend`에
`patches` 파라미터를 넘기면 특정 패치만 필터링해서 계산합니다. 다만 이 기능이 추가되기 전에
수집된 기존 데이터는 패치 정보가 없어(`patch IS NULL`) 필터링 대상에서 빠지므로, 새로 데이터를
수집해야 의미가 생깁니다.

**픽 순서에 따른 가중치(t)**: 드래프트가 진행될수록(아군/상대 픽이 많이 드러날수록) 시너지·카운터
보정치의 신뢰도를 높여서 더 크게 반영합니다 (`_progress_weight`, `draft_progress_ramp`). 반대로
밴 회피 보정은 드래프트 초반(선픽)일수록 크게, 후픽으로 갈수록 0에 가깝게 줄어듭니다
(`ban_safety_weight`) — 이미 밴 페이즈가 끝났거나 후픽이라 밴당할 위험이 의미 없어졌기 때문입니다.

**밴 회피**: 매치 데이터의 밴 정보(`champion_bans` 테이블)로 챔피언별 밴률을 계산해서, 후보 풀
평균 밴률보다 낮은 챔피언에 가산점을 줍니다. 밴 정보도 패치와 마찬가지로 이 기능 추가 이후
수집된 매치에만 있어서, 기존 데이터로는 밴률이 0으로 나옵니다.

**팀 정렬 보정 (실측 데이터 기반, 아군이 1명 이상 있을 때만 계산)**: "포킹/스플릿/한타" 같은
챔피언 아키타입은 Riot API에 없어서 수동 태깅이 필요한데, 그건 제외하고 실제로 매치 데이터에서
그대로 뽑히는 세 가지만 반영합니다.
- **데미지 다양성**: 챔피언별 물리/마법/고정 데미지 실측 비율(`damage_profiles`)로, 아군이
  이미 한쪽으로 쏠려 있으면(예: 전부 물리 딜러) 반대 성향 챔피언에 가산점을 줍니다.
- **CC 보완**: 챔피언별 분당 CC 기여도 실측치(`cc_contribution`)로, 아군의 CC가 부족하면
  CC를 많이 주는 챔피언에 가산점을 줍니다.
- **타이밍 정렬**: 게임 길이 구간별(초반<20분/후반≥30분) 실측 승률 격차(`power_curve`)로,
  아군과 같은 타이밍에 강한 챔피언에 가산점을 줍니다.

이 세 지표도 새로 추가한 컬럼(`physical_damage`, `magic_damage`, `true_damage`,
`time_ccing_others`, `game_duration_sec`)이 필요해서, 패치/밴 정보와 마찬가지로 이 기능
추가 이후 수집된 매치부터 반영됩니다.

나중에 로지스틱 회귀 등 다른 모델로 바꾸더라도 API 응답 형태는 그대로 유지되도록
`scorer.py`에 계산 로직을 분리해뒀습니다.

### 아직 안 붙인 것

- 티어(브론즈~마스터+) 구간별 승률 — 지금은 챌린저/그랜드마스터 단일 구간만 수집합니다.
- 팀 조합 아키타입(포킹/스플릿/한타 등) 자체의 분류 — 객관적인 소스가 없어서 보류.
- 유저 개인 전적/최근 폼/숙련도 기반 개인화 — 계정 연동이 필요한 별도 기능입니다.
- 잔여 픽/밴 예측 — 아직 없습니다.

## 구조

- `backend/` — FastAPI 서버 + 매치 수집 스크립트 + SQLite
- `frontend/` — React(Vite) 웹앱

`backend/data_seed.db`(배포용 시드 DB)는 [Git LFS](https://git-lfs.com/)로 관리됩니다.
클론할 때 내용이 필요하면 `git lfs install` 후 클론하세요 (`brew install git-lfs` 필요할 수 있음).
안 깔려 있어도 코드 실행/개발에는 지장 없고, 실제 배포용 DB만 못 받아옵니다.

## 1. Riot API 키 발급

1. https://developer.riotgames.com/ 에서 라이엇 계정으로 로그인 (계정이 없으면 직접 가입해야 합니다)
2. 로그인 후 대시보드에서 "Personal API Key" 발급 (24시간마다 만료되어 재발급 필요)
3. `backend/.env.example`을 `backend/.env`로 복사하고 키를 채워넣기

```bash
cd backend
cp .env.example .env
# .env 파일 열어서 RIOT_API_KEY=발급받은키 로 수정
```

## 2. 백엔드 실행

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 데이터 수집 (챌린저/그마 소환사 20명 기준 매치 수집, 시간 좀 걸림)
python -m app.collector --max-summoners 20 --matches-per-summoner 10

# API 서버 실행
uvicorn app.main:app --reload --port 8000
```

`app.collector`는 Riot API 개인 키의 요청 제한(2분당 100회)에 맞춰 자동으로 속도를 조절합니다.
더 많은 데이터가 필요하면 `--max-summoners`, `--matches-per-summoner` 값을 늘려서 여러 번 실행하면 됩니다
(이미 처리한 매치는 건너뜁니다).

## 2-1. (선택) LCK 등 프로 대회 데이터 추가

Riot 공식 API에는 e스포츠 경기 기록이 없어서, 커뮤니티가 관리하는
[Oracle's Elixir](https://oracleselixir.com/tools/downloads)에서 CSV를 받아 넣습니다.

1. 위 페이지에서 원하는 시즌의 CSV를 다운로드
2. 아래 명령으로 적재 (LCK만 넣고 싶으면 `--league LCK`, 전체는 생략)

```bash
cd backend
source venv/bin/activate
python -m app.load_pro_data --csv ~/Downloads/2025_LoL_esports_match_data.csv --league LCK
```

솔로랭크 데이터와 프로 데이터는 `source` 컬럼(`soloq` / `pro:LCK`)으로 구분되어 같이 쌓입니다.
`/api/draft/recommend` 호출 시 `sources` 값을 지정하면 특정 소스만 골라서 계산할 수 있습니다.

## 2-2. 데이터 주기적으로 업데이트하기

메타는 계속 바뀌니까 데이터도 주기적으로 갱신해야 합니다. `backend/update_data.sh`가
`app.collector`를 돌려서 최신 솔로랭크 매치를 더 수집해줍니다 (이미 처리한 매치는
건너뛰므로 여러 번 실행해도 안전).

```bash
cd backend
./update_data.sh
# 수집 규모를 바꾸고 싶으면:
MAX_SUMMONERS=100 MATCHES_PER_SUMMONER=20 ./update_data.sh
```

실행 로그는 `backend/update.log`에 쌓입니다.

**⚠️ 완전 자동화의 한계**: Riot Personal API Key는 24시간마다 만료되고, 재발급은
developer.riotgames.com에 로그인해서 버튼을 눌러야 하는 수동 작업이라 스크립트로 자동화할
수 없습니다. 즉 `update_data.sh`를 cron 등으로 주기 실행하게 걸어놔도, 키가 만료된 뒤로는
계속 실패만 합니다. 방법은 두 가지입니다:

1. **간단한 방법(권장)**: 그냥 생각날 때마다 (또는 하루 시작할 때) 키를 갱신하고
   `./update_data.sh`를 수동 실행. 서버 배포 없이 로컬에서 바로 되는 방법입니다.
2. **주기 실행 + 매일 키 갱신 병행**: 아래처럼 cron에 등록해두고, 매일 아침 `.env`의
   `RIOT_API_KEY`만 새로 발급받아 갈아끼우면 나머지는 자동으로 돌아갑니다.

   ```bash
   crontab -e
   # 매일 새벽 4시에 실행하는 예시 (경로는 본인 환경에 맞게 수정)
   0 4 * * * /Users/kimminjae/Documents/League\ of\ Legends/lol-banpick-helper/backend/update_data.sh
   ```

   장기적으로 매번 수동 갱신이 귀찮다면, Riot Developer Portal에서 앱을 등록해
   만료 없는 "Personal"/"Production" API 키를 신청하는 방법도 있습니다(승인 필요, 발급까지
   시간이 걸릴 수 있음).

## 3. 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173` 접속. `/api` 요청은 Vite 프록시를 통해 `localhost:8000` 백엔드로 전달됩니다.

## 밴픽 순서

프론트에서 두 가지 순서 중 골라서 진행할 수 있습니다:

- **솔로랭크 순서**: 밴 10개(양팀 번갈아 5개씩) → 픽 10개(1-2-2-2-2-1 스네이크)
- **대회 순서**: 밴 6개(B-R-B-R-B-R) → 픽 6개(B-R-R-B-B-R) → 밴 4개(R-B-R-B) → 픽 4개(R-B-B-R)

## 실시간 연동 (로컬 브리지)

실제 게임 클라이언트에서 밴/픽이 일어나는 대로 웹 페이지에 자동 반영하고 싶다면
`bridge/lcu_bridge.py`를 게임을 켤 PC에서 실행하세요. 롤 클라이언트가 로컬에 열어두는
비공식 관리 API(LCU)를 읽어서 배포된 백엔드로 상태를 전송합니다.

**PC방 등 Python 설치가 안 되는 환경**: 아래 링크에서 Windows용 실행 파일(exe)을
바로 받아서 더블클릭만 하면 됩니다 (설치 불필요).

👉 [lcu_bridge.exe 다운로드](https://github.com/Kminj2296/lol-banpick-helper/releases/download/bridge-latest/lcu_bridge.exe)

`bridge/` 코드가 바뀔 때마다 GitHub Actions가 이 exe를 자동으로 새로 빌드해서
같은 링크에 올려두므로, 항상 이 링크 하나만 기억하면 됩니다.

**Python이 있는 환경(직접 실행)**:

```bash
cd bridge
pip install -r requirements.txt
python lcu_bridge.py
# 다른 백엔드 주소를 쓰려면:
BACKEND_URL=https://내주소 python lcu_bridge.py
```

웹 페이지의 밴픽 시뮬레이터에서 "실시간 연동" 체크박스를 켜면, 브리지가 보내는 상태가
그대로 반영되면서(수동 입력 칸은 숨겨지고 추천 표만 계속 갱신됩니다) 화면에 표시됩니다.

- 브라우저 JS만으로는 롤 클라이언트의 로컬 API에 접근할 수 없어서, PC에 이 스크립트를
  따로 실행해둬야 합니다.
- PC방처럼 보안 프로그램이 임의 실행 파일을 막는 환경에서는 안 될 수도 있습니다. 그럴 땐
  기존처럼 시뮬레이터에서 수동으로 입력하면 됩니다.

## API

- `GET /api/lanes` — 라인 목록
- `GET /api/champions` — 수집된 챔피언 목록 (영문 ID)
- `GET /api/champion-names` — 챔피언 영문 ID → 한국어 이름 매핑 (Riot Data Dragon 기준,
  `backend/app/data/champion_names_ko.json`)
- `GET /api/champion-images` — 챔피언 영문 ID → 썸네일 이미지 URL 매핑 (Riot Data Dragon CDN,
  `backend/app/data/champion_images.json`)
- `GET /api/sources` — 적재된 데이터 소스 목록 (soloq, pro:LCK 등)과 경기 수
- `GET /api/top-champions?min_games=5&sources=soloq` — 라인 구분 없는 전체 챔피언 승률 순위 (밴 추천용)
- `GET /api/recommend?lane=TOP&enemy_champion=Darius&min_games=5` — 같은 라인 1대1 상대 기준 카운터 픽
- `POST /api/draft/recommend` — 드래프트 상태를 받아 다음 픽 추천
  ```json
  {
    "lane": "TOP",
    "allies": ["Leona"],
    "enemies": ["Jinx"],
    "banned": ["Azir"],
    "min_games": 5,
    "sources": null
  }
  ```
