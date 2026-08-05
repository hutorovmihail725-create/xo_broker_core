import aiosqlite
from typing import Optional

DB_PATH = "xo_base.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_slots (
    user_id        INTEGER NOT NULL,
    slot_index     INTEGER NOT NULL,
    region         TEXT,
    city           TEXT,
    district       TEXT DEFAULT 'Все районы',
    property_type  TEXT,
    land_status    TEXT DEFAULT 'Нет',
    min_price      INTEGER,
    max_price      INTEGER,
    PRIMARY KEY (user_id, slot_index)
);
"""


async def init_db() -> None:
    """Создает таблицу user_slots, если она еще не существует."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TABLE_SQL)
        await db.commit()


async def ensure_user(user_id: int) -> None:
    """
    Регистрирует пользователя, создавая пустую строку под слот №1
    (личный контур), если для него еще нет ни одной записи.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM user_slots WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if row[0] == 0:
            await db.execute(
                """
                INSERT INTO user_slots (user_id, slot_index, district, land_status)
                VALUES (?, 1, 'Все районы', 'Нет')
                """,
                (user_id,),
            )
            await db.commit()


async def update_slot(user_id: int, slot_index: int, **fields) -> None:
    """
    Обновляет (или создает, если не было) строку слота указанными полями.
    Пример: await update_slot(123, 1, region="Московская обл.", city="Куровское")
    """
    if not fields:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM user_slots WHERE user_id = ? AND slot_index = ?",
            (user_id, slot_index),
        )
        exists = await cursor.fetchone()

        if exists:
            set_clause = ", ".join(f"{key} = ?" for key in fields)
            values = list(fields.values()) + [user_id, slot_index]
            await db.execute(
                f"UPDATE user_slots SET {set_clause} WHERE user_id = ? AND slot_index = ?",
                values,
            )
        else:
            columns = ["user_id", "slot_index"] + list(fields.keys())
            placeholders = ", ".join(["?"] * len(columns))
            values = [user_id, slot_index] + list(fields.values())
            await db.execute(
                f"INSERT INTO user_slots ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
        await db.commit()


async def get_slot(user_id: int, slot_index: int) -> Optional[dict]:
    """Возвращает словарь с данными конкретного слота или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM user_slots WHERE user_id = ? AND slot_index = ?",
            (user_id, slot_index),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_slots(user_id: int) -> list[dict]:
    """Возвращает список всех слотов пользователя (для бизнес-контура)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM user_slots WHERE user_id = ? ORDER BY slot_index",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

