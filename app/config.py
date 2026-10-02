import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_ids: set[int] = field(
        default_factory=lambda: {
            int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
        }
    )
    webapp_url: str = os.getenv("WEBAPP_URL", "").rstrip("/")
    port: int = int(os.getenv("PORT", "8080"))
    db_path: str = os.getenv("DB_PATH", str(BASE_DIR / "data" / "bot.db"))
    debug: bool = os.getenv("DEBUG", "0") == "1"
    webapp_dir: Path = BASE_DIR / "webapp"
    uploads_dir: Path = BASE_DIR / "data" / "uploads"


config = Config()
