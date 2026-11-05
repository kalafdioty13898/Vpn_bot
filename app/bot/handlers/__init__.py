"""Router registration."""
from aiogram import Router

from app.bot.handlers import (
    my_services,
    purchase,
    receipts,
    referral,
    start,
    support,
    trial,
    tutorial,
    wallet,
)
from app.bot.handlers.admin import (
    input as admin_input,
    panel as admin_panel,
    panelcfg as admin_panelcfg,
    prices as admin_prices,
    settings as admin_settings,
    tutorials_admin,
    users_admin,
)


def setup_routers() -> Router:
    root = Router(name="root")

    # --- Admin routers (باید اول باشند تا فیلتر ادمین روی اولویت اجرا شود) ---
    admin_root = Router(name="admin_root")
    admin_root.include_router(admin_panel.router)
    admin_root.include_router(admin_settings.router)
    admin_root.include_router(admin_prices.router)
    admin_root.include_router(admin_panelcfg.router)
    admin_root.include_router(users_admin.router)
    admin_root.include_router(admin_input.router)
    admin_root.include_router(tutorials_admin.router)

    # --- User routers ---
    user_root = Router(name="user_root")
    user_root.include_router(start.router)
    user_root.include_router(purchase.router)
    user_root.include_router(receipts.router)
    user_root.include_router(wallet.router)
    user_root.include_router(my_services.router)
    user_root.include_router(trial.router)
    user_root.include_router(referral.router)
    user_root.include_router(support.router)
    user_root.include_router(tutorial.router)

    root.include_router(admin_root)
    root.include_router(user_root)
    return root
