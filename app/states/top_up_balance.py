from aiogram.fsm.state import State, StatesGroup

class TopUpBalanceState(StatesGroup):
    get_amount = State()