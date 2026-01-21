from aiogram.fsm.state import State, StatesGroup

class MailingState(StatesGroup):
    get_message = State()
    get_filters = State()
    pre_check = State()
    start_mailing = State()