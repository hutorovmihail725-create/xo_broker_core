import os
import aiohttp
import logging

logger = logging.getLogger("xo_broker.ai_diplomat")

class XOAIDiplomat:
    def __init__(self):
        # Чтение API-ключа OpenRouter из переменных окружения Railway
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.api_url = "https://openrouter.ai"

    async def generate_negotiation_script(self, object_title: str, price: int, region: str, discount: int):
        """Асинправная генерация индивидуального скрипта торга на основе уязвимостей лота"""
        if not self.api_key or "placeholder" in self.api_key:
            # Безопасный резервный локальный сценарий, если баланс OpenRouter равен 0
            return (
                f"🤖 **Локальный скрипт торга под объект:** {object_title}\n\n"
                f"1. **Точка давления**: Объект в регионе {region.title()} продается с дисконтом -{discount}%. "
                f"Продавец явно торопится, деньги нужны срочно.\n"
                f"2. **Аргумент для звонка**: 'Здравствуйте. Вижу ваш лот за {price} руб. Знаю средний рынок района. "
                f"Готов выйти на сделку за 3 дня с наличными, если скинете еще 7% от текущей цены.'\n"
                f"3. **Защита**: Если откажет — берите паузу на 24 часа. Он перезвонит сам."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com",
            "Content-Type": "application/json"
        }

        prompt = (
            f"Ты — жесткий, прагматичный B2B риелтор-дипломат. Напиши пошаговый индивидуальный скрипт телефонного торга "
            f"для покупки недвижимости ниже рынка. Объект: {object_title}, Текущая цена: {price} рублей, "
            f"Регион: {region}, Вычисленный дисконт: -{discount}%. Выдай 3 конкретные фразы для сбивания цены, основываясь на том, "
            f"что продавец спешит. Пиши коротко, емко, только деловой пацанский прагматизм, без глянца и вежливости."
        )

        payload = {
            "model": "anthropic/claude-3.5-sonnet:beta",
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['choices'][0]['message']['content']
                    else:
                        logger.error(f"Ошибка API OpenRouter: Статус {response.status}")
                        return "⚠️ Ошибка связи с ИИ-сервером OpenRouter. Используйте базовую тактику торга наличными."
        except Exception as e:
            logger.error(f"Критический сбой модуля ИИ-Дипломат: {e}")
            return "⚠️ Не удалось сгенерировать скрипт торга. Проверьте сетевое подключение контейнера."
