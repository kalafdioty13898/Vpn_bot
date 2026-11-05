"""Wallet service — transaction-safe balance operations."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Wallet, WalletTransaction
from app.services.user_service import get_wallet

logger = logging.getLogger(__name__)


async def adjust_balance(
    session: AsyncSession,
    user_id: int,
    amount: int,
    tx_type: str,
    reference: str = "",
) -> int | None:
    """موجودی را با Row Lock تغییر می‌دهد. اگر موجودی کافی نباشد None برمی‌گرداند.

    amount مثبت = شارژ، منفی = برداشت. هرگز Double Spending نمی‌کند.
    """
    if amount == 0:
        return None

    wallet = await get_wallet(session, user_id)
    if amount < 0 and wallet.balance + amount < 0:
        return None

    wallet.balance += amount
    session.add(
        WalletTransaction(
            user_id=user_id,
            amount=amount,
            tx_type=tx_type,
            reference=reference,
            balance_after=wallet.balance,
        )
    )
    await session.flush()
    logger.info("Wallet %s: %+d -> %d (%s)", user_id, amount, wallet.balance, tx_type)
    return wallet.balance


async def get_balance(session: AsyncSession, user_id: int) -> int:
    wallet = await session.scalar(select(Wallet).where(Wallet.user_id == user_id))
    return wallet.balance if wallet else 0
