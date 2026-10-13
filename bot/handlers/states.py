from aiogram.fsm.state import State, StatesGroup

class UploadStates(StatesGroup):
    uploading_photos = State()

class PaymentStates(StatesGroup):
    waiting_email = State()

