"""FSM states."""
from aiogram.fsm.state import State, StatesGroup


class PurchaseStates(StatesGroup):
    waiting_username = State()
    waiting_custom_volume = State()
    waiting_custom_days = State()


class ReceiptStates(StatesGroup):
    waiting_file = State()


class WalletStates(StatesGroup):
    waiting_amount = State()


class SupportStates(StatesGroup):
    waiting_message = State()


class ServiceSearchStates(StatesGroup):
    waiting_username = State()


class AdminStates(StatesGroup):
    """فیلد موردي که ادمین باید بفرستد در data['field'] نگهداری می‌شود."""

    waiting_value = State()
