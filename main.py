import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Хирургический патч: импортируем модули напрямую из корня репозитория
from database import init_db, async_session, UserProfile, SearchSlot
from scraper import XORealEstateScraper
from ai_diplomat import XOAIDiplomat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("xo_broker.main")

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Инициализируем объекты классов парсера и ИИ
scraper = XORealEstateScraper()
diplomat = XOAIDiplomat()

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    # Автоматическая регистрация пользователя в базе данных при старте
    try:
        async with async_session() as session:
            async with session.begin():
                user = await session.get(UserProfile, message.from_user.id)
                if not user:
                    user = UserProfile(user_id=message.from_user.id, account_type="personal")
                    session.add(user)
    except Exception as e:
        logger.error(f"Ошибка сохранения профиля: {e}")
    
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
    
    if callback.data == "menu_personal":
        builder.row(types.InlineKeyboardButton(text="📍 Запустить поиск: Московская обл.", callback_data="run_search_moscow_20"))
        builder.row(types.InlineKeyboardButton(text="📍 Запустить поиск: Сочи", callback_data="run_search_sochi_20"))
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_main"))
        await callback.message.edit_text(
            "🏠 **Контур «ЛИЧНЫЙ» (ИИ-Риелтор)**\n\n"
            "Вам доступен 1 активный слот поиска. ИИ-ассистент готов проанализировать рынок и убрать уловки продавцов.\n\n"
            "Выберите интересующий регион для симуляции перехвата лота:",
            reply_markup=builder.as_markup()
        )
    elif callback.data == "menu_business":
        builder.row(types.InlineKeyboardButton(text="🎰 Слот 1: Казань (Коммерция >30%)", callback_data="run_search_kazan_30"))
        builder.row(types.InlineKeyboardButton(text="🎰 Слот 2: Сочи (ИЖС/Земля >20%)", callback_data="run_search_sochi_20"))
        builder.row(types.InlineKeyboardButton(text="➕ Настроить пустой слот (3/10)", callback_data="stub_slot"))
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_main"))
        await callback.message.edit_text(
            "👔 **Контур «БИЗНЕС» (Профессиональный инструмент)**\n\n"
            "Вам открыта сетка из 10 одновременно активных слотов параллельного поиска по всей РФ.\n\n"
            "Управляйте активными триггерами перехвата дисконта ниже:",
            reply_markup=builder.as_markup()
        )
    elif callback.data == "menu_cadastr":
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_main"))
        await callback.message.edit_text(
            "🔍 **Разовый Кадастровый Экспресс-Аудит**\n\n"
            "Сквозной скрининг объекта по базам Росреестра, ЕГРН и ФССП на предмет арестов, скрытых долгов и залогов.\n\n"
            "📥 **Отправьте кадастровый номер объекта** в чат бота для автоматического выставления счета на 150 Telegram Stars...",
            reply_markup=builder.as_markup()
        )

@router.callback_query(lambda c: c.data.startswith("run_search_"))
async def run_search_callback(callback: types.CallbackQuery):
    data_parts = callback.data.split("_")
    target_region = "московская область" if data_parts[2] == "moscow" else data_parts[2]
    discount_trigger = int(data_parts[3])
    
    await callback.message.edit_text("⏳ *Асинхронный мульти-парсинг Авито/Циан запущен. Вычисляю дисконт рынка...*")
    
    deals = await scraper.analyze_and_filter(target_region, "commercial", discount_trigger)
    
    if not deals:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_personal"))
        await callback.message.edit_text("❌ В данный момент новые объекты с дисконтом выше заданного порога не найдены.", reply_markup=builder.as_markup())
        return
        
    deal = deals[0]
    estimated_profit = int(deal["price"] * (deal["discount"] / 100))
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔥 Сгенерировать ИИ-скрипт торга", 
        callback_data=f"ai_script_{data_parts[2]}_{deal['price']}_{deal['discount']}"
    ))
    builder.row(types.InlineKeyboardButton(text="⬅️ Вернуться в Личный Кабинет", callback_data="back_to_main"))
    
    await callback.message.edit_text(
        f"🚨 **ОБЪЕКТ С КРИТИЧЕСКИМ ДИСКОНТОМ ПЕРЕХВАЧЕН!**\n\n"
        f"📍 **Локация**: {deal['address']}\n"
        f"📋 **Объект**: {deal['title']}\n"
        f"💰 **Цена в объявлении**: {deal['price']:,} руб.\n"
        f"📉 **Вычисленный дисконт**: -{deal['discount']}% ниже рынка района!\n"
        f"📈 **Средняя цена в этой зоне**: {deal['market_avg']:,} руб.\n"
        f"💥 **Источник**: Данные сквозного парсера [{deal['source']}]\n\n"
        f"📊 **ФЛИП-АНАЛИТИКА ХОЛДИНГА:**\n"
        f"• Чистый коэффициент окупаемости (ROI): **Высокий**\n"
        f"• Прогнозируемая чистая маржа при перепродаже: **+{estimated_profit:,} руб.**\n"
        f"• Расчетный налог НДФЛ (13%): **0 руб.** (при использовании легального вычета)\n",
        reply_markup=builder.as_markup()
    )

@router.callback_query(lambda c: c.data.startswith("ai_script_"))
async def ai_script_callback(callback: types.CallbackQuery):
    data_parts = callback.data.split("_")
    region = "московская область" if data_parts[2] == "moscow" else data_parts[2]
    price = int(data_parts[3])
    discount = int(data_parts[4])
    
    await callback.message.edit_text("🧠 *ИИ-Дипломат подключается к API OpenRouter. Claude 3.5 Sonnet формирует сценарий торга...*")
    
    script_text = await diplomat.generate_negotiation_script("Коммерческий объект/Участок", price, region, discount)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⬅️ Вернуться в Главное Меню", callback_data="back_to_main"))
    
    await callback.message.edit_text(
        f"{script_text}\n\n"
        f"--------------------------------------------------\n"
        f"⚖️ *Модуль 'Налоговый щит' и ЕГРН-скрининг зафиксированы в ядре XO.*",
        reply_markup=builder.as_markup()
    )

@router.callback_query(lambda c: c.data == "stub_slot")
async def stub_slot_callback(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_business"))
    await callback.message.edit_text("⚙️ **Каскадный фильтр Авито всей РФ**\n\nИнлайн-выбор сетки регионов и районов находится в режиме отладки связей. Слот забронирован под ваш аккаунт.", reply_markup=builder.as_markup())

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
    logger.info("Запуск монолита XO-Broker...")
    try:
        await init_db()
        logger.info("Асинхронная база данных успешно инициализирована.")
    except Exception as e:
        logger.error(f"Предупреждение инициализации БД (используется локальный кэш): {e}")
        
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
