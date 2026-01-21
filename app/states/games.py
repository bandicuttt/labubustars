from aiogram.fsm.state import State, StatesGroup

class GameState(StatesGroup):
    get_bet = State()