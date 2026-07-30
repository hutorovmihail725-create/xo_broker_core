import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("xo_broker")

# Чтение токена прямо из настроек Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "⚡️ **XO-Broker Global v2.4 активирован**.\n\n"
        "Личный кабинет запущен. Система парсинга Авито/Циан по всей РФ готова к конфигурации слотов."
    )

async def main():
    logger.info("Запуск XO-Broker...")
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
