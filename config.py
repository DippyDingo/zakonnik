from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    token: str
    db_path: Path
    timezone: ZoneInfo
    mastered_streak: int
    cards_file: Path


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Не найден TELEGRAM_BOT_TOKEN. Создайте .env на основе .env.example."
        )

    timezone_name = os.getenv("BOT_TIMEZONE", "Europe/Moscow").strip()
    db_path = Path(os.getenv("DB_PATH", "bot_data.sqlite3")).expanduser()
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path

    mastered_streak = int(os.getenv("MASTERED_STREAK", "3"))

    return Settings(
        token=token,
        db_path=db_path,
        timezone=ZoneInfo(timezone_name),
        mastered_streak=mastered_streak,
        cards_file=BASE_DIR / "data" / "cards.json",
    )
