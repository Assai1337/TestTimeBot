from aiogram.fsm.state import StatesGroup, State

class TestStates(StatesGroup):
    TESTING = State()
    EDITING = State()
    CONFIRM_FINISH = State()
    VIEWING_TESTS = State()
    VIEWING_ATTEMPTS = State()
    VIEWING_ATTEMPT_DETAILS = State()
