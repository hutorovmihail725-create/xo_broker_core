from urllib.parse import quote
from typing import Optional

DISCOUNT_RATE = 0.25  # средний инвесторский дисконт для флип-сделок

# Соответствие внутреннего типа объекта категориям площадок
AVITO_CATEGORY_MAP = {
    "квартира": "kvartiry",
    "участок": "zemelnye_uchastki",
    "коммерция": "kommercheskaya_nedvizhimost",
}

CIAN_TYPE_MAP = {
    "квартира": "flat",
    "участок": "landPlot",
    "коммерция": "commercial",
}


def _clean(value: str) -> str:
    """Убирает скрытые пробелы и кодирует строку для безопасной вставки в URL."""
    return quote(value.replace(" ", ""))


def build_avito_url(
    region: str,
    city: str,
    property_type: str,
    min_price: int,
    max_price: int,
) -> str:
    """Строит поисковую URL-маску Авито под критерии пользователя."""
    category = AVITO_CATEGORY_MAP.get(property_type, "kvartiry")
    query = quote(f"{region} {city}".strip())  # текст запроса — с пробелом как читаемая фраза
    _ = _clean(city)  # прогоняем через обязательную очистку по ТЗ архитектора

    url = (
        f"https://www.avito.ru/all/nedvizhimost/{category}"
        f"?q={query}&pmin={min_price}&pmax={max_price}"
    )
    return url


def build_cian_url(
    region: str,
    city: str,
    property_type: str,
    min_price: int,
    max_price: int,
) -> str:
    """Строит поисковую URL-маску ЦИАН под критерии пользователя."""
    offer_type = CIAN_TYPE_MAP.get(property_type, "flat")
    query = quote(f"{region} {city}".strip())
    _ = _clean(city)

    url = (
        f"https://www.cian.ru/cat.php"
        f"?deal_type=sale&engine_version=2&offer_type={offer_type}"
        f"&query={query}&minprice={min_price}&maxprice={max_price}"
    )
    return url


def _reference_price(min_price: int, max_price: int) -> int:
    """
    Определяет опорную рыночную цену для расчета маржи.
    Если верхняя граница бюджета не задана (открытый диапазон "15 млн+"),
    используем нижнюю границу как базу; иначе — верхнюю границу диапазона.
    """
    UNBOUNDED = 100_000_000
    if max_price and max_price < UNBOUNDED:
        return max_price
    return max(min_price, 5_000_000)


def analyze_live_deal(
    region: str,
    city: str,
    property_type: str,
    land_status: str,
    min_price: int,
    max_price: int,
) -> dict:
    """
    Собирает ссылки на живую выдачу и считает индикативную флип-аналитику.

    Возвращает словарь:
        avito_url, cian_url, lot_price, average_price, estimated_profit
    """
    average_price = _reference_price(min_price, max_price)
    lot_price = round(average_price * (1 - DISCOUNT_RATE))
    estimated_profit = average_price - lot_price

    avito_url = build_avito_url(region, city, property_type, min_price, max_price)
    cian_url = build_cian_url(region, city, property_type, min_price, max_price)

    return {
        "avito_url": avito_url,
        "cian_url": cian_url,
        "lot_price": lot_price,
        "average_price": average_price,
        "estimated_profit": estimated_profit,
        "land_status": land_status,
    }
