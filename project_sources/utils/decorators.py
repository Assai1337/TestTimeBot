from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from functools import wraps
import logging

from tools.states import TestStates

logger = logging.getLogger(__name__)

def check_active_test(handler):
    @wraps(handler)
    async def wrapper(callback: types.CallbackQuery, state: FSMContext, *args, **kwargs):
        user_data = await state.get_data()
        current_state = await state.get_state()
        if not user_data or 'test_id' not in user_data or current_state not in [TestStates.TESTING.state,
                                                                                TestStates.CONFIRM_FINISH.state,
                                                                                TestStates.EDITING.state]:
            # Пользователь не в активном тесте
            await callback.answer("Ваше тестирование не активно.")

            # Получаем message_id и chat_id
            message_id = callback.message.message_id
            chat_id = callback.message.chat.id

            # Создаём клавиатуру с неактивными кнопками (например, для завершения теста)
            disabled_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Завершить тест (недоступно)", callback_data="noop")
                ]
            ])

            try:
                # Редактируем сообщение, делая кнопку неактивной
                await callback.message.bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=disabled_keyboard
                )
                logger.debug("Disabled test buttons successfully.")
            except Exception as e:
                logger.error(f"Ошибка при редактировании кнопок: {e}")

            return  # Прерываем выполнение обработчика
        return await handler(callback, state, *args, **kwargs)

    return wrapper
