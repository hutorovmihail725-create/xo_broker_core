import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, String, BigInteger, Integer, Boolean, ForeignKey

# Получаем защищенную строку подключения от Railway
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id = Column(BigInteger, primary_key=True)
    account_type = Column(String, default="personal")  # personal / business
    is_active = Column(Boolean, default=True)

class SearchSlot(Base):
    __tablename__ = "search_slots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user_profiles.user_id"))
    slot_index = Column(Integer)  # 1 для личных, 1-10 для бизнеса
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    district = Column(String, nullable=True)
    property_type = Column(String, nullable=True)  # commercial / land / residential
    discount_trigger = Column(Integer, default=20)  # процент дисконта (>10, >20, >30)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
