"""Central logging configuration. Never logs secrets."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"

# مقادیری که هرگز نباید لاگ شوند
SECRET_KEYS = {"password", "api_key", "token", "bot_token", "card_number"}


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        msg = record.getMessage()
        lowered = msg.lower()
        for key in SECRET_KEYS:
            # فقط جلوی لاگ شدن مقدار بعد از = را می‌گیرد
            if f"{key}=" in lowered:
                record.msg = msg + " [REDACTED]"
                record.args = None
                break
        return True


def setup_logging(level: str = "INFO") -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(SecretFilter())

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    console_handler.addFilter(SecretFilter())

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.addHandler(file_handler)
    # کنسول همیشه فعال باشد — در GitHub Actions لاگ‌ها فقط از این مسیر دیده می‌شوند
    root.addHandler(console_handler)

    # کاهش نویز کتابخانه‌ها
    for noisy in ("aiogram.event", "aiosqlite", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
