import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("xo_broker")

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🏠 Личный контур (ИИ-Риелтор)", callback_data="menu_personal"))
    builder.row(types.InlineKeyboardButton(text="👔 Бизнес контур (Риелторы / 10 слотов)", callback_data="menu_business"))
    builder.row(types.InlineKeyboardButton(text="🔍 Разовая проверка по кадастру", callback_data="menu_cadastr"))
    
    await message.answer(
        "⚡️ **XO-Broker Global v2.4 активирован**.\n\n"
        "Добро пожаловать в Личный Кабинет платформы недвижимости РФ. Выберите режим работы системы:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(lambda c: c.data.startswith("menu_"))
async def menu_callbacks(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_main"))
    
    if callback.data == "menu_personal":
        await callback.message.edit_text(
            "🏠 **Контур «ЛИЧНЫЙ» (ИИ-Риелтор)**\n\n"
            "Доступен 1 активный слот поиска.\n"
            "ИИ-ассистент готов анализировать скрытые юридические уловки в описаниях объявлений Авито/Циан.\n\n"
            "⚙️ *Модуль настройки гео-локации компилируется...*",
            reply_markup=builder.as_markup()
        )
    elif callback.data == "menu_business":
        await callback.message.edit_text(
            "👔 **Контур «БИЗНЕС» (Для крупных игроков)**\n\n"
            "Вам открыто 10 одновременно активных слотов параллельного поиска.\n"
            "Система готова вести круглосуточный мульти-парсинг Авито, Циан, Домклик и Торгов по банкротству.\n\n"
            "🎰 *Доступные слоты: 0/10. Настройка каскадных фильтров компилируется...*",
            reply_markup=builder.as_markup()
        )
    elif callback.data == "menu_cadastr":
        await callback.message.edit_text(
            "🔍 **Разовый Кадастровый Экспресс-Аудит**\n\n"
            "Стоимость одной сквозной проверки по базам ЕГРН, Росреестра и ФССП составляет 150 Telegram Stars.\n\n"
            "📥 *Отправьте кадастровый номер объекта в ответном сообщении для выставления счета...*",
            reply_markup=builder.as_markup()
        )

@router.callback_query(lambda c: c.data == "back_to_main")
async def back_callback(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🏠 Личный контур (ИИ-Риелтор)", callback_data="menu_personal"))
    builder.row(types.InlineKeyboardButton(text="👔 Бизнес контур (Риелторы / 10 слотов)", callback_data="menu_business"))
    builder.row(types.InlineKeyboardButton(text="🔍 Разовая проверка по кадастру", callback_data="menu_cadastr"))
    
    await callback.message.edit_text(
        "⚡️ **XO-Broker Global v2.4 активирован**.\n\n"
        "Добро пожаловать в Личный Кабинет платформы недвижимости РФ. Выберите режим работы системы:",
        reply_markup=builder.as_markup()
    )

async def main():
    logger.info("Запуск XO-Broker с расширенным меню...")
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

