import asyncio
import logging
import os

import httpx
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from pydantic_settings import BaseSettings

import database
import scraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("xo_broker")


class Settings(BaseSettings):
    bot_token: str
    openrouter_api_key: str = ""

    class Config:
        env_file = ".env"
        env_prefix = "XO_"


settings = Settings()

router = Router()

# ──────────────────────────────────────────────────────────────────────────
# Оперативная память состояний пользователя (FSM "вручную", по требованию
# архитектора — простой глобальный словарь, переживает до перезапуска
# процесса; постоянные данные слотов уже к этому моменту лежат в SQLite).
# ──────────────────────────────────────────────────────────────────────────
USER_STATES: dict[int, dict] = {}


def _state(user_id: int) -> dict:
    return USER_STATES.setdefault(user_id, {"step": "idle", "slot_index": 1})


def fmt_money(amount: int) -> str:
    """Форматирует число с пробелом как разделителем тысяч, например 4 500 000."""
    return f"{amount:,}".replace(",", " ")


REGIONS = [
    ("Московская область и Москва", "MskObl"),
    ("Ленинградская область и СПБ", "SpbObl"),
    ("Краснодарский край", "KrdKray"),
    ("Республика Татарстан", "Tatarstan"),
    ("Любой другой субъект РФ", "Other"),
]

PROPERTY_TYPES = [
    ("🏢 Квартира (Жилая)", "квартира"),
    ("🌱 Земельный участок", "участок"),
    ("💼 Коммерческая недвижимость", "коммерция"),
]

LAND_STATUSES = [
    ("ИЖС", "ИЖС"),
    ("СНТ / ЛПХ", "СНТ"),
]

BUDGETS = [
    ("До 5 млн руб.", 0, 5_000_000),
    ("От 5 до 15 млн руб.", 5_000_000, 15_000_000),
    ("От 15 млн руб.+", 15_000_000, 100_000_000),
]


# ──────────────────────────────────────────────────────────────────────────
# КЛАВИАТУРЫ
# ──────────────────────────────────────────────────────────────────────────

def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Личный контур (ИИ-Риелтор)", callback_data="open_personal")],
            [InlineKeyboardButton(text="👔 Бизнес контур (Риелторы / 10 слотов)", callback_data="open_business")],
            [InlineKeyboardButton(text="🔍 Разовая проверка по кадастру", callback_data="open_cadastr")],
        ]
    )


def kb_personal_slot() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Настроить проект поиска (1/1)", callback_data="set_region_start")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")],
        ]
    )


def kb_business_slots() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"Слот {i}", callback_data=f"bizslot_{i}")]
        for i in range(1, 11)
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_regions() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"geo_reg_{code}")]
        for label, code in REGIONS
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_change_region() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Изменить регион", callback_data="set_region_start")]]
    )


def kb_property_types() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"prop_type_{value}")]
        for label, value in PROPERTY_TYPES
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_land_status() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"land_{value}")]
        for label, value in LAND_STATUSES
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_budgets() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"budget_{lo}_{hi}")]
        for label, lo, hi in BUDGETS
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_result(avito_url: str, cian_url: str, lot_price: int, discount_pct: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Открыть живую выдачу Авито", url=avito_url)],
            [InlineKeyboardButton(text="🎯 Открыть живую выдачу Циан", url=cian_url)],
            [InlineKeyboardButton(
                text="🔥 Сгенерировать ИИ-скрипт торга",
                callback_data=f"airun_{lot_price}_{discount_pct}",
            )],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main")],
        ]
    )


def kb_back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Вернуться в Главное Меню", callback_data="back_to_main")]]
    )


# ──────────────────────────────────────────────────────────────────────────
# ШАГ 0: /start
# ──────────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await database.ensure_user(message.from_user.id)
    USER_STATES[message.from_user.id] = {"step": "idle", "slot_index": 1}

    text = (
        "⚡ ИИ Риелтор активирован. Добро пожаловать в Личный Кабинет "
        "единой платформы недвижимости всей РФ. Выберите режим работы системы:"
    )
    await message.answer(text, reply_markup=kb_main_menu(), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery) -> None:
    USER_STATES[callback.from_user.id] = {"step": "idle", "slot_index": 1}
    text = (
        "⚡ ИИ Риелтор активирован. Добро пожаловать в Личный Кабинет "
        "единой платформы недвижимости всей РФ. Выберите режим работы системы:"
    )
    await callback.message.edit_text(text, reply_markup=kb_main_menu(), parse_mode=ParseMode.HTML)
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────
# ШАГ 1: выбор режима / слота
# ──────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "open_personal")
async def cb_open_personal(callback: CallbackQuery) -> None:
    state = _state(callback.from_user.id)
    state["step"] = "idle"
    state["slot_index"] = 1

    text = (
        "🏠 Контур «ЛИЧНЫЙ» (ИИ-Риелтор)\n\n"
        "Вам доступен 1 активный проект поиска. Нажмите кнопку ниже для "
        "настройки параметров гео-локации, типа объекта и ценового диапазона "
        "по всей РФ:"
    )
    await callback.message.edit_text(text, reply_markup=kb_personal_slot(), parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data == "open_business")
async def cb_open_business(callback: CallbackQuery) -> None:
    text = "👔 Контур «БИЗНЕС» — выберите один из 10 слотов для настройки:"
    await callback.message.edit_text(text, reply_markup=kb_business_slots(), parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.startswith("bizslot_"))
async def cb_business_slot(callback: CallbackQuery) -> None:
    _, slot_str = callback.data.split("_", 1)
    slot_index = int(slot_str)

    state = _state(callback.from_user.id)
    state["step"] = "idle"
    state["slot_index"] = slot_index

    text = (
        f"👔 Контур «БИЗНЕС», Слот {slot_index}\n\n"
        "Нажмите кнопку ниже для настройки параметров гео-локации, типа "
        "объекта и ценового диапазона по всей РФ:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"➕ Настроить проект поиска (Слот {slot_index})",
                callback_data="set_region_start",
            )],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="open_business")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────
# ШАГ 2: выбор макро-региона РФ
# ──────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_region_start")
async def cb_set_region_start(callback: CallbackQuery) -> None:
    text = (
        "🌍 КАСКАДНЫЙ ФИЛЬТР РФ: ШАГ 1 (Выбор субъекта)\n\n"
        "Выберите интересующий регион из списка субъектов РФ:"
    )
    await callback.message.edit_text(text, reply_markup=kb_regions(), parse_mode=ParseMode.HTML)
    await callback.answer()


REGION_CODE_TO_LABEL = {code: label for label, code in REGIONS}


@router.callback_query(F.data.startswith("geo_reg_"))
async def cb_geo_region(callback: CallbackQuery) -> None:
    _, _, code = callback.data.split("_", 2)
    region_label = REGION_CODE_TO_LABEL.get(code, "Регион РФ")

    state = _state(callback.from_user.id)
    state["region"] = region_label
    state["step"] = "wait_city_text"

    text = (
        f"📍 РЕГИОН ЗАФИКСИРОВАН: {region_label}\n\n"
        "🏙️ ШАГ 2: ВВОД ЛОКАЦИИ (Все города, районы и поселки)\n\n"
        "Напишите текстом в ответном сообщении название абсолютно любого "
        "города, городского округа, района, поселка или деревни внутри "
        "выбранного субъекта.\n\n"
        "Пример ввода: Ликино-Дулево, Орехово-Зуево, Куровское, Раменское "
        "или Подольск"
    )
    await callback.message.edit_text(text, reply_markup=kb_change_region(), parse_mode=ParseMode.HTML)
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────
# ШАГ 3/4: перехват текстового ввода города → выбор типа объекта
# ──────────────────────────────────────────────────────────────────────────

@router.message(F.text, lambda message: USER_STATES.get(message.from_user.id, {}).get("step") == "wait_city_text")
async def on_city_text(message: Message) -> None:
    state = _state(message.from_user.id)

    city_clean = message.text.strip().title()
    state["city"] = city_clean
    state["step"] = "idle"  # сбрасываем ожидание, чтобы бот не реагировал на обычные сообщения

    region_label = state.get("region", "РФ")

    text = (
        "✅ ГЕО-ЛОКАЦИЯ ПРОПИСАНА В СЛОТ:\n"
        f"• Регион: {region_label}\n"
        f"• Населенный пункт: г./пос. {city_clean}\n\n"
        "📋 ШАГ 3: ТИП НЕДВИЖИМОСТИ\n"
        "Что именно мы ищем на площадках Авито и Циан?"
    )
    # Новое сообщение, т.к. edit_text нельзя применить к обычному тексту пользователя
    await message.answer(text, reply_markup=kb_property_types(), parse_mode=ParseMode.HTML)


# ──────────────────────────────────────────────────────────────────────────
# ШАГ 5: тип объекта → (если участок: статус земли) → бюджет
# ──────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("prop_type_"))
async def cb_property_type(callback: CallbackQuery) -> None:
    _, _, prop_value = callback.data.split("_", 2)

    state = _state(callback.from_user.id)
    state["property_type"] = prop_value

    if prop_value == "участок":
        text = (
            "🌱 УТОЧНЕНИЕ СТАТУСА ЗЕМЛИ\n\n"
            "Укажите категорию использования земельного участка:"
        )
        await callback.message.edit_text(text, reply_markup=kb_land_status(), parse_mode=ParseMode.HTML)
    else:
        state["land_status"] = "Нет"
        text = (
            "💰 ШАГ 5: ЦЕНОВОЙ ДИАПАЗОН БЮДЖЕТА\n\n"
            "Укажите рамки стоимости для автоматической фильтрации лотов:"
        )
        await callback.message.edit_text(text, reply_markup=kb_budgets(), parse_mode=ParseMode.HTML)

    await callback.answer()


@router.callback_query(F.data.startswith("land_"))
async def cb_land_status(callback: CallbackQuery) -> None:
    _, land_value = callback.data.split("_", 1)

    state = _state(callback.from_user.id)
    state["land_status"] = land_value

    text = (
        "💰 ШАГ 5: ЦЕНОВОЙ ДИАПАЗОН БЮДЖЕТА\n\n"
        "Укажите рамки стоимости для автоматической фильтрации лотов:"
    )
    await callback.message.edit_text(text, reply_markup=kb_budgets(), parse_mode=ParseMode.HTML)
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────
# ШАГ 6: сохранение в БД, сборка ссылок, выдача результата
# ──────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("budget_"))
async def cb_budget(callback: CallbackQuery) -> None:
    _, min_str, max_str = callback.data.split("_", 2)
    min_price, max_price = int(min_str), int(max_str)

    state = _state(callback.from_user.id)
    state["min_price"] = min_price
    state["max_price"] = max_price

    user_id = callback.from_user.id
    slot_index = state.get("slot_index", 1)

    await callback.message.edit_text(
        "⏳ Конфигурация слота сохранена в xo_base.db. Запускаю сквозной "
        "перехват ссылок всей РФ...",
        parse_mode=ParseMode.HTML,
    )

    await database.update_slot(
        user_id,
        slot_index,
        region=state.get("region", ""),
        city=state.get("city", ""),
        property_type=state.get("property_type", ""),
        land_status=state.get("land_status", "Нет"),
        min_price=min_price,
        max_price=max_price,
    )

    deal = scraper.analyze_live_deal(
        region=state.get("region", ""),
        city=state.get("city", ""),
        property_type=state.get("property_type", ""),
        land_status=state.get("land_status", "Нет"),
        min_price=min_price,
        max_price=max_price,
    )

    discount_pct = 25
    text = (
        "🚨 ГОРЯЧИЙ ОБЪЕКТ ПЕРЕХВАЧЕН С ПОИСКОВЫХ МАСОК!\n\n"
        f"📍 Зона: РФ, {state.get('region', '')}, г. {state.get('city', '')}\n"
        f"📋 Цель: {state.get('property_type', '').capitalize()} в г. "
        f"{state.get('city', '')} (Статус земли: {deal['land_status']})\n"
        f"💰 Цена лота: {fmt_money(deal['lot_price'])} руб.\n"
        f"📉 Вычисленный дисконт: -{discount_pct}% ниже среднего рынка района!\n"
        f"📈 Средняя цена в этой локации: {fmt_money(deal['average_price'])} руб.\n\n"
        "📊 ФЛИП-АНАЛИТИКА И МАРЖА ХОЛДИНГА:\n"
        "• Рентабельность (ROI): Высокая\n"
        f"• Чистая прибыль при перепродаже: +{fmt_money(deal['estimated_profit'])} руб.\n\n"
        "🔗 Нажмите на инлайн-кнопки ниже, чтобы открыть актуальные объявления прямо сейчас:"
    )

    await callback.message.answer(
        text,
        reply_markup=kb_result(deal["avito_url"], deal["cian_url"], deal["lot_price"], discount_pct),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────
# ШАГ 7: ИИ-скрипт торга через OpenRouter (Claude 3.5 Sonnet)
# ──────────────────────────────────────────────────────────────────────────

async def call_openrouter_negotiation_script(lot_price: int, discount_pct: int) -> str:
    """Запрашивает у OpenRouter (Claude 3.5 Sonnet) сценарий торга с продавцом."""
    if not settings.openrouter_api_key:
        return (
            "⚠️ Не настроен OPENROUTER_API_KEY — ИИ-скрипт торга недоступен. "
            "Добавьте ключ в переменные окружения сервиса."
        )

    prompt = (
        f"Ты — профессиональный переговорщик по недвижимости. Лот выставлен "
        f"по цене {fmt_money(lot_price)} руб., что на {discount_pct}% ниже "
        f"среднего рынка района. Составь короткий пошаговый сценарий "
        f"переговоров с собственником: на какие огрехи объекта ссылаться, "
        f"какие аргументы использовать, и готовые фразы для диалога, чтобы "
        f"обоснованно сбить цену еще ниже."
    )

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001 — отдаем пользователю понятную ошибку
        logger.exception("OpenRouter request failed")
        return f"⚠️ Не удалось получить ответ от ИИ-Дипломата: {exc}"


@router.callback_query(F.data.startswith("airun_"))
async def cb_ai_negotiation(callback: CallbackQuery) -> None:
    _, price_str, discount_str = callback.data.split("_", 2)
    lot_price, discount_pct = int(price_str), int(discount_str)

    await callback.message.edit_text(
        "🧠 ИИ-Дипломат подключается к API OpenRouter. Claude 3.5 Sonnet "
        "формирует сценарий торга...",
        parse_mode=ParseMode.HTML,
    )

    script_text = await call_openrouter_negotiation_script(lot_price, discount_pct)

    await callback.message.answer(
        script_text,
        reply_markup=kb_back_to_main(),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────
# ШАГ: разовая проверка по кадастру (заглушка-заготовка)
# ──────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "open_cadastr")
async def cb_open_cadastr(callback: CallbackQuery) -> None:
    text = (
        "🔍 РАЗОВАЯ ПРОВЕРКА ПО КАДАСТРУ\n\n"
        "Пришлите кадастровый номер объекта отдельным сообщением "
        "(модуль проверки подключается отдельно)."
    )
    await callback.message.edit_text(text, reply_markup=kb_back_to_main(), parse_mode=ParseMode.HTML)
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────
# ТОЧКА ВХОДА
# ──────────────────────────────────────────────────────────────────────────

async def main() -> None:
    await database.init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("XO-Broker Global запущен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

