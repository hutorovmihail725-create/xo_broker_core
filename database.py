import os
import aiosqlite

DB_FILE = "xo_base.db"

async def init_db():
    """Инициализация таблиц внутри локального файла xo_base.db"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Таблица профилей пользователей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                account_type TEXT DEFAULT 'personal',
                current_step TEXT DEFAULT 'main'
            )
        ''')
        # Таблица 10 активных слотов поиска для каждого пользователя
        await db.execute('''
            CREATE TABLE IF NOT EXISTS search_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                slot_index INTEGER,
                region TEXT,
                city TEXT,
                district TEXT,
                property_type TEXT,
                land_status TEXT,
                min_price INTEGER,
                max_price INTEGER,
                discount_trigger INTEGER DEFAULT 20,
                is_active INTEGER DEFAULT 0
            )
        ''')
        await db.commit()

async def register_user(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user_id,))
        # Сразу создаем 10 пустых слотов для управления
        for i in range(1, 11):
            await db.execute("""
                INSERT OR IGNORE INTO search_slots (user_id, slot_index) 
                VALUES (?, ?)
            """, (user_id, i))
        await db.commit()

async def update_slot(user_id: int, slot_index: int, field: str, value):
    async with aiosqlite.connect(DB_FILE) as db:
        query = f"UPDATE search_slots SET {field} = ?, is_active = 1 WHERE user_id = ? AND slot_index = ?"
        await db.execute(query, (value, user_id, slot_index))
        await db.commit()

async def get_slots(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT * FROM search_slots WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchall()
