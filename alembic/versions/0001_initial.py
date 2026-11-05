"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ساخت کامل اسکیما با create_all (idempotent)
    from app.db.models import Base
    Base.metadata.create_all(bind=op.get_bind())

    # seed اولیه
    from app.db.init_db import seed_defaults
    import asyncio

    bind = op.get_bind()
    try:
        asyncio.run(seed_defaults_with(bind))
    except RuntimeError:
        # داخل event loop دیگر: seed در استارتاپ ربات انجام می‌شود
        pass


def seed_defaults_with(bind):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.db.init_db import seed_defaults
    engine = create_async_engine(bind.engine.url.render_as_string(hide_password=False))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async def run():
        async with factory() as session:
            await seed_defaults(session)
        await engine.dispose()
    return run()


def downgrade() -> None:
    from app.db.models import Base
    Base.metadata.drop_all(bind=op.get_bind())
