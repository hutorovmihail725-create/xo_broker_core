import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database
from scraper import XORealEstateScraper
from ai_diplomat import XOAIDiplomat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("xo_broker.main")

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

scraper = XORealEstateScraper()
diplomat = XOAIDiplomat()

USER_STATES = {}

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    await database.init_db()
    await database.register_user(message.from_user.id)
    USER_STATES.pop(message.from_user.id, None)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🏠 Личный контур (ИИ-Риелтор)", callback_data="open_personal"))
    builder.row(types.InlineKeyboardButton(text="👔 Бизнес контур (Риелторы / 10 слотов)", callback_data="open_business"))
    builder.row(types.InlineKeyboardButton(text="🔍 Разовая проверка по кадастру", callback_data="open_cadastr"))
    
    await message.answer(
        "⚡️ **ИИ Риелтор активирован**.\n\n"
        "Добро пожаловать в Личный Кабинет единой платформы недвижимости всей РФ. Выберите режим работы системы:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    USER_STATES.pop(callback.from_user.id, None)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🏠 Личный контур (ИИ-Риелтор)", callback_data="open_personal"))
    builder.row(types.InlineKeyboardButton(text="👔 Бизнес контур (Риелторы / 10 слотов)", callback_data="open_business"))
    builder.row(types.InlineKeyboardButton(text="🔍 Разовая проверка по кадастру", callback_data="open_cadastr"))
    await callback.message.edit_text("⚡️ **ИИ Риелтор активирован**.\n\nВыберите режим работы системы:", reply_markup=builder.as_markup())
@router.callback_query(lambda c: c.data in ["open_personal", "open_business"])
async def open_counters(callback: types.CallbackQuery):
    account_type = "personal" if callback.data == "open_personal" else "business"
    USER_STATES[callback.from_user.id] = {"account_type": account_type, "slot_index": 1, "step": "idle"}
    
    builder = InlineKeyboardBuilder()
    if account_type == "personal":
        builder.row(types.InlineKeyboardButton(text="➕ Настроить проект поиска (1/1)", callback_data="set_region_start"))
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"))
        await callback.message.edit_text("🏠 **Контур «ЛИЧНЫЙ» (ИИ-Риелтор)**\n\nВам доступен 1 активный проект поиска. Нажмите кнопку ниже для настройки параметров гео-локации, типа объекта и ценового диапазона по всей РФ:", reply_markup=builder.as_markup())
    else:
        for i in range(1, 6):
            builder.row(types.InlineKeyboardButton(text=f"🎰 Слот {i}", callback_data=f"set_slot_{i}"), types.InlineKeyboardButton(text=f"🎰 Слот {i+5}", callback_data=f"set_slot_{i+5}"))
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"))
        await callback.message.edit_text("👔 **Контур «БИЗНЕС» (Для крупных игроков)**\n\nВам доступно 10 одновременно активных слотов параллельного поиска. Выберите пустой слот для пошаговой конфигурации целей:", reply_markup=builder.as_markup())

@router.callback_query(lambda c: c.data.startswith("set_slot_") or c.data == "set_region_start")
async def set_slot_index(callback: types.CallbackQuery):
    if callback.data.startswith("set_slot_"):
        slot_idx = int(callback.data.split("_"))
        USER_STATES[callback.from_user.id] = {"account_type": "business", "slot_index": slot_idx, "step": "idle"}
        
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Московская область и Москва", callback_data="geo_reg_MskObl"))
    builder.row(types.InlineKeyboardButton(text="Ленинградская область и СПБ", callback_data="geo_reg_SpbObl"))
    builder.row(types.InlineKeyboardButton(text="Краснодарский край", callback_data="geo_reg_KrdKray"))
    builder.row(types.InlineKeyboardButton(text="Республика Татарстан", callback_data="geo_reg_Tatarstan"))
    builder.row(types.InlineKeyboardButton(text="Нижегородская область", callback_data="geo_reg_NizhObl"))
    builder.row(types.InlineKeyboardButton(text="Свердловская область", callback_data="geo_reg_SverdObl"))
    builder.row(types.InlineKeyboardButton(text="Любой другой субъект РФ", callback_data="geo_reg_Other"))
    builder.row(types.InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_main"))
    builder.adjust(2, 2, 2, 1, 1)
    
    await callback.message.edit_text("🌍 **КАСКАДНЫЙ ФИЛЬТР РФ: ШАГ 1 (Выбор субъекта)**\n\nВыберите интересующий регион из списка 89 субъектов РФ:", reply_markup=builder.as_markup())
@router.callback_query(lambda c: c.data.startswith("geo_reg_"))
async def geo_reg_callback(callback: types.CallbackQuery):
    reg_key = callback.data.split("_")
    region_name = "Московская обл." if reg_key == "MskObl" else "Ленинградская обл." if reg_key == "SpbObl" else "Краснодарский край" if reg_key == "KrdKray" else "Татарстан" if reg_key == "Tatarstan" else "РФ"
    
    USER_STATES[callback.from_user.id]["region"] = region_name
    USER_STATES[callback.from_user.id]["step"] = "wait_city_text"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⬅️ Изменить регион", callback_data="set_region_start"))
    
    await callback.message.edit_text(
        f"📍 **РЕГИОН ЗАФИКСИРОВАН**: {region_name}\n\n"
        f"🏙️ **ШАГ 2: ВВОД ЛОКАЦИИ (Все города, районы и поселки)**\n\n"
        f"Напишите текстом в ответном сообщении название абсолютно **любого города, городского округа, района, поселка или деревни** внутри выбранного субъекта.\n\n"
        f"*Пример ввода: Ликино-Дулево, Орехово-Зуево, Шатура, Раменское или Балашиха*",
        reply_markup=builder.as_markup()
    )

@router.message(lambda m: USER_STATES.get(m.from_user.id, {}).get("step") == "wait_city_text")
async def process_city_text(message: types.Message):
    user_input = message.text.strip().title()
    USER_STATES[message.from_user.id]["city"] = user_input
    USER_STATES[message.from_user.id]["district"] = "Все районы"
    USER_STATES[message.from_user.id]["step"] = "idle"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🏢 Квартира (Жилая)", callback_data="prop_type_квартира"))
    builder.row(types.InlineKeyboardButton(text="🌱 Земельный участок", callback_data="prop_type_участок"))
    builder.row(types.InlineKeyboardButton(text="💼 Коммерческая недвижимость", callback_data="prop_type_коммерция"))
    
    await message.answer(
        f"✅ **ГЕО-ЛОКАЦИЯ ПРОПИСАНА В СЛОТ:**\n"
        f"• Регион: {USER_STATES[message.from_user.id]['region']}\n"
        f"• Населенный пункт/Район: {user_input}\n\n"
        f"📋 **ШАГ 3: ТИП НЕДВИЖИМОСТИ**\n"
        f"Что именно мы ищем на площадках Авито и Циан?",
        reply_markup=builder.as_markup()
    )

@router.callback_query(lambda c: c.data.startswith("prop_type_"))
async def prop_type_callback(callback: types.CallbackQuery):
    pt_name = callback.data.split("_")
    USER_STATES[callback.from_user.id]["property_type"] = pt_name
    
    if pt_name == "участок":
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="ИЖС (Индивидуальное строительство)", callback_data="land_st_ИЖС"))
        builder.row(types.InlineKeyboardButton(text="СНТ / ЛПХ / Сельхоз", callback_data="land_st_СНТ"))
        await callback.message.edit_text("🌱 **ШАГ 4: СТАТУС ЗЕМЕЛЬНЫХ УЧАСТКОВ**\n\nКакая категория назначения земли требуется?", reply_markup=builder.as_markup())
    else:
        USER_STATES[callback.from_user.id]["land_status"] = "Нет"
        await ask_budget_handler(callback)

@router.callback_query(lambda c: c.data.startswith("land_st_"))
async def land_st_callback(callback: types.CallbackQuery):
    USER_STATES[callback.from_user.id]["land_status"] = callback.data.split("_")
    await ask_budget_handler(callback)
async def ask_budget_handler(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="До 5 млн руб.", callback_data="budget_0_5000000"))
    builder.row(types.InlineKeyboardButton(text="От 5 до 15 млн руб.", callback_data="budget_5000000_15000000"))
    builder.row(types.InlineKeyboardButton(text="От 15 млн руб.+", callback_data="budget_15000000_100000000"))
    await callback.message.edit_text("💰 **ШАГ 5: ЦЕНОВОЙ ДИАПАЗОН БЮДЖЕТА**\n\nУкажите рамки стоимости для автоматической фильтрации лотов:", reply_markup=builder.as_markup())

@router.callback_query(lambda c: c.data.startswith("budget_"))
async def budget_callback(callback: types.CallbackQuery):
    data_parts = callback.data.split("_")
    min_p = int(data_parts[1])
    max_p = int(data_parts[2])
    
    state = USER_STATES.get(callback.from_user.id)
    if not state:
        await callback.message.answer("⚠️ Ошибка сессии. Пропишите /start заново.")
        return
    
    try:
        await database.update_slot(callback.from_user.id, state["slot_index"], "region", state["region"])
        await database.update_slot(callback.from_user.id, state["slot_index"], "city", state["city"])
        await database.update_slot(callback.from_user.id, state["slot_index"], "district", state["district"])
        await database.update_slot(callback.from_user.id, state["slot_index"], "property_type", state["property_type"])
        await database.update_slot(callback.from_user.id, state["slot_index"], "land_status", state["land_status"])
        await database.update_slot(callback.from_user.id, state["slot_index"], "min_price", min_p)
        await database.update_slot(callback.from_user.id, state["slot_index"], "max_price", max_p)
    except Exception as e:
        logger.error(f"Предупреждение сохранения в БД: {e}")
    
    await callback.message.edit_text("⏳ *Конфигурация слота сохранена в xo_base.db. Запускаю сквозной перехват ссылок всей РФ...*")
    
    deal = await scraper.analyze_live_deal(state["region"], state["city"], state["district"], state["property_type"], min_p, max_p)
    estimated_profit = int(deal["price"] * (deal["discount"] / 100))
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔥 Сгенерировать ИИ-скрипт торга", callback_data=f"airun_{deal['price']}_{deal['discount']}"))
    builder.row(types.InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main"))
    
    await callback.message.edit_text(
        f"🚨 **ГОРЯЧИЙ ОБЪЕКТ ПЕРЕХВАЧЕН С ПОИСКОВЫХ МАСОК!**\n\n"
        f"📍 **Зона**: {deal['address']}\n"
        f"📋 **Цель**: {deal['title']} (Статус земли: {state['land_status']})\n"
        f"💰 **Цена лота**: {deal['price']:,} руб.\n"
        f"📉 **Вычисленный дисконт**: -{deal['discount']}% ниже среднего рынка района!\n"
        f"📈 **Средняя цена в этой локации**: {deal['market_avg']:,} руб.\n\n"
        f"📊 **ФЛИП-АНАЛИТИКА И МАРЖА ХОЛДИНГА:**\n"
        f"• Рентабельность (ROI): **Высокая**\n"
        f"• Чистая прибыль при перепродаже: **+{estimated_profit:,} руб.**\n\n"
        f"🔗 **ПРЯМЫЕ ССЫЛКИ НА ПЛОЩАДКИ С ФИЛЬТРАМИ:**\n"
        f"• [Смотреть выдачу на Авито]({deal['avito_url']})\n"
        f"• [Смотреть выдачу на Циан]({deal['cian_url']})\n",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

@router.callback_query(lambda c: c.data.startswith("airun_"))
async def ai_run_callback(callback: types.CallbackQuery):
    data_parts = callback.data.split("_")
    price = int(data_parts[1])
    discount = int(data_parts[2])
    state = USER_STATES.get(callback.from_user.id, {"city": "Выбранный город", "property_type": "Объект"})
    
    await callback.message.edit_text("🧠 *ИИ-Дипломат подключается к API OpenRouter. Claude 3.5 Sonnet формирует сценарий торга...*")
    script_text = await diplomat.generate_negotiation_script(state["property_type"], price, state["city"], discount)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⬅️ Вернуться в Главное Меню", callback_data="back_to_main"))
    await callback.message.edit_text(f"{script_text}", reply_markup=builder.as_markup())

@router.callback_query(lambda c: c.data == "open_cadastr")
async def open_cadastr_callback(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"))
    await callback.message.edit_text("🔍 **Разовый Кадастровый Экспресс-Аудит**\n\n📥 **Отправьте кадастровый номер объекта** в чат бота для автоматического выставления счета на 150 Telegram Stars...", reply_markup=builder.as_markup())

async def main():
    logger.info("Запуск обновленного монолита XO-Broker...")
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


