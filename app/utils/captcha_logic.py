import random
import string

from typing import Optional

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import CAPTCHA_SYMBOLS, ActiveCaptchas, CaptchaData, CAPTCHA_SUM, CAPTCHA_LENGTH
from loader import bot

async def send_new_captcha(user_id: int) -> None:
    """Отправляет новую капчу пользователю"""
    answer, token, markup = build_captcha_kb()
    message = await bot.send_message(
        chat_id=user_id,
        text=f"🔐 Выберите: {answer}",
        reply_markup=markup
    )
    storage.add(user_id, (answer, token, message.message_id))

async def delete_old_captcha(chat_id: int, message_id: int) -> None:
    """Удаляет предыдущую капчу"""
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

async def verify_captcha(
    user_id: int, 
    message_id: int, 
    token: str
) -> bool:
    """Проверяет валидность капчи"""
    data = storage.get(user_id)
    if not data or data[2] != message_id:
        return False
    
    _, correct_token, _ = data
    digits = [int(c) for c in token if c.isdigit()]
    return sum(digits) == 5 and token == correct_token

class CaptchaStorage:
    def __init__(self):
        self._storage: ActiveCaptchas = {}

    def add(self, user_id: int, data: CaptchaData) -> None:
        self._storage[user_id] = data

    def get(self, user_id: int) -> Optional[CaptchaData]:
        return self._storage.get(user_id)

    def remove(self, user_id: int) -> None:
        self._storage.pop(user_id, None)

storage = CaptchaStorage()


def generate_token() -> str:
    """Генерирует токен с заданной суммой цифр"""
    while True:
        token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=CAPTCHA_LENGTH))
        digits = [int(c) for c in token if c.isdigit()]
        if digits and sum(digits) == CAPTCHA_SUM:
            return token

def generate_fake_token() -> str:
    """Генерирует невалидный токен"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=CAPTCHA_LENGTH))

def build_captcha_kb():
    """Создает новую капчу и возвращает (answer, token, markup)"""
    answer = random.choice(CAPTCHA_SYMBOLS)
    token = generate_token()
    
    builder = InlineKeyboardBuilder()
    for emoji in random.sample(CAPTCHA_SYMBOLS, len(CAPTCHA_SYMBOLS)):
        callback_data = f"captcha:{token if emoji == answer else generate_fake_token()}"
        builder.button(text=emoji, callback_data=callback_data)
    
    builder.adjust(3)  # 3 кнопки в ряд
    return answer, token, builder.as_markup()