from aiogram.fsm.state import State, StatesGroup

class ReferralState(StatesGroup):
    get_ref = State()
    get_price = State()
    get_admin = State()