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
    # Admin panel manzili (bo'sh bo'lsa WEBAPP_URL/admin/)
    admin_url: str = os.getenv("ADMIN_URL", "").rstrip("/")
    # Boshqa domendagi (shared hosting) sahifalarga API ruxsati, vergul bilan
    cors_origins: set[str] = field(
        default_factory=lambda: {
            x.strip().rstrip("/") for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()
        }
    )
    port: int = int(os.getenv("PORT", "8080"))
    db_path: str = os.getenv("DB_PATH", str(BASE_DIR / "data" / "bot.db"))
    debug: bool = os.getenv("DEBUG", "0") == "1"
    webapp_dir: Path = BASE_DIR / "webapp"
    uploads_dir: Path = BASE_DIR / "data" / "uploads"


config = Config()
