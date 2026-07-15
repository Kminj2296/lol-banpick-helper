# 롤 밴픽 도우미

상대가 어떤 챔피언을 픽했는지에 따라, 라인별로 승률이 좋은 카운터 픽을 추천해주는 웹앱입니다.

lol.ps 같은 스크래핑 사이트 대신, **Riot 공식 API로 챌린저/그랜드마스터 랭크 게임 데이터를 직접 수집**해서
라인별 "챔피언 vs 상대 챔피언" 승률을 자체 집계합니다.

## 구조

- `backend/` — FastAPI 서버 + 매치 수집 스크립트 + SQLite
- `frontend/` — React(Vite) 웹앱

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

## 3. 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173` 접속. `/api` 요청은 Vite 프록시를 통해 `localhost:8000` 백엔드로 전달됩니다.

## API

- `GET /api/lanes` — 라인 목록
- `GET /api/champions` — 수집된 챔피언 목록
- `GET /api/recommend?lane=TOP&enemy_champion=Darius&min_games=5` — 해당 라인에서 상대 챔피언 기준 승률 높은 순 추천
