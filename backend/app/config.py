import os

from dotenv import load_dotenv

load_dotenv()

RIOT_API_KEY = os.environ.get("RIOT_API_KEY", "")
PLATFORM = os.environ.get("PLATFORM", "kr")
REGION = os.environ.get("REGION", "asia")

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data.db"))

QUEUE_RANKED_SOLO = 420
LANES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
