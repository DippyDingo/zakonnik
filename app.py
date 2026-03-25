from __future__ import annotations

import logging
import time
from pathlib import Path

from bot import CriminalCodeBot
from config import load_settings
from database import Database
from telegram.error import NetworkError, RetryAfter, TimedOut


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    log_file = base_dir / "bot.log"
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    settings = load_settings()
    db = Database(settings.db_path, mastered_streak=settings.mastered_streak)
    inserted = db.seed_cards(settings.cards_file)
    logger = logging.getLogger(__name__)
    logger.info("Cards seeded: %s", inserted)
    logger.info("Bot log file: %s", log_file)

    retry_delay = 10
    while True:
        try:
            bot = CriminalCodeBot(settings, db)
            application = bot.build_application()
            application.run_polling(
                allowed_updates=["message", "callback_query"],
                connect_timeout=30,
                pool_timeout=30,
                read_timeout=30,
                write_timeout=30,
                close_loop=False,
            )
            retry_delay = 10
        except RetryAfter as exc:
            delay = max(int(exc.retry_after), retry_delay)
            logger.warning("Telegram requested retry after %s seconds", delay)
            time.sleep(delay)
        except (TimedOut, NetworkError) as exc:
            logger.warning(
                "Network issue while starting or polling Telegram: %s. Retry in %s seconds.",
                exc,
                retry_delay,
            )
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        except KeyboardInterrupt:
            logger.info("Bot stopped by keyboard interrupt")
            break


if __name__ == "__main__":
    main()
