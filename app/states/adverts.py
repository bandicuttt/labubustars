from aiogram.fsm.state import State, StatesGroup

class AdvertState(StatesGroup):
    get_message = State()
    get_settings = State()
