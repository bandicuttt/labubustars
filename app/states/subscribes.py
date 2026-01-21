from aiogram.fsm.state import State, StatesGroup

class SubscribeState(StatesGroup):
    get_subscribe_type = State()
    get_subscribe_data = State()