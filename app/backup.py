"""Baza va yuklangan rasmlarning zaxira nusxasi (zip) — menejerga Telegram orqali yuboriladi."""
import asyncio
import io
import logging
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile

from . import db
from .config import config
from .utils import now

log = logging.getLogger(__name__)
BACKUP_HOUR = 4  # har kuni soat 04:00 (Toshkent)


async def make_backup() -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory() as tmp:
        db_copy = Path(tmp) / "bot.db"
        # ishlab turgan bazaning izchil nusxasi
        await db.db().execute("VACUUM INTO ?", (str(db_copy),))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_copy, "data/bot.db")
            if config.uploads_dir.exists():
                for f in config.uploads_dir.iterdir():
                    if f.is_file():
                        zf.write(f, f"data/uploads/{f.name}")
    name = f"yaproq_backup_{now().strftime('%Y%m%d_%H%M')}.zip"
    return buf.getvalue(), name


async def send_backup(bot: Bot, chat_ids) -> None:
    data, name = await make_backup()
    caption = (
        "💾 <b>Zaxira nusxa</b>\n"
        f"Hajmi: {len(data) / 1024:.0f} KB\n\n"
        "Tiklash: botni to'xtating, arxivdagi <code>data/</code> papkasini loyiha papkasiga "
        "qo'ying va botni qayta ishga tushiring."
    )
    for chat_id in chat_ids:
        try:
            await bot.send_document(chat_id, BufferedInputFile(data, filename=name), caption=caption)
        except Exception as e:
            log.warning("Backup yuborilmadi %s: %s", chat_id, e)


async def daily_backup_loop(bot: Bot) -> None:
    while True:
        n = now()
        target = n.replace(hour=BACKUP_HOUR, minute=0, second=0, microsecond=0)
        if target <= n:
            target += timedelta(days=1)
        await asyncio.sleep((target - n).total_seconds())
        try:
            await send_backup(bot, config.admin_ids)
        except Exception:
            log.exception("Kunlik backup xatosi")
