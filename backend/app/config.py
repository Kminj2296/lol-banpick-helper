import os

from dotenv import load_dotenv

load_dotenv()

RIOT_API_KEY = os.environ.get("RIOT_API_KEY", "")
PLATFORM = os.environ.get("PLATFORM", "kr")
REGION = os.environ.get("REGION", "asia")

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data.db"))
# data.db는 .gitignore/.railwayignore 대상이라 배포 환경엔 안 실려있을 수 있다.
# 그런 경우 배포에 같이 올라간 시드 파일(data_seed.db)로 최초 1회 채워 넣는다.
DB_SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "data_seed.db")

QUEUE_RANKED_SOLO = 420
LANES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
