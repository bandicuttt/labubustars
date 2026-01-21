from aiogram.fsm.state import State, StatesGroup

class PromocodeState(StatesGroup):
    get_message = State()
    get_settings = State()
