from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = "sqlite+aiosqlite:///./invoice_agent.db"

engine = create_async_engine(DATABASE_URL)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


class StoredTask(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    principal: Mapped[str] = mapped_column(String(64), index=True)
    context_id: Mapped[str] = mapped_column(String(100), index=True)
    batch_id: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(40))
    task_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))

    __table_args__ = (
        UniqueConstraint("principal", "id", name="uq_principal_task"),
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    principal: Mapped[str] = mapped_column(String(64), index=True)
    message_id: Mapped[str] = mapped_column(String(200))
    message_hash: Mapped[str] = mapped_column(String(64))
    task_id: Mapped[str] = mapped_column(String(100))

    __table_args__ = (
        UniqueConstraint(
            "principal",
            "message_id",
            name="uq_principal_message",
        ),
    )


async def initialize_database():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)