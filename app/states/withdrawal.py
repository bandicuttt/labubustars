from aiogram.fsm.state import State, StatesGroup

class WithdrawalState(StatesGroup):
    get_amount = State()