# handlers/results.py

import json
from typing import Optional, List, Dict, Any
from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
import logging

from tools.models import TestAttempt, Test, User, Question
from .main_menu import get_main_menu  # Импорт функции главного меню
from tools.states import TestStates  # Импорт состояний из states.py

router = Router()

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(handler)

ITEMS_PER_PAGE = 8  # Количество элементов на странице


# Вспомогательная функция для проверки, находится ли пользователь в состоянии тестирования
async def is_user_testing(state: FSMContext) -> bool:
    current_state = await state.get_state()
    testing_states = [
        TestStates.TESTING.state,
        TestStates.EDITING.state,
        TestStates.CONFIRM_FINISH.state
    ]
    return current_state in testing_states


def create_tests_keyboard(tests: List[Test], passed_tests_ids: List[int], page: int, total_pages: int,
                          active: bool = True) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с тестами и кнопками навигации.
    Добавляет галочку ✅ к тестам, которые пользователь успешно прошёл хотя бы один раз.
    Если active=False, кнопки будут неактивны.
    """
    buttons = []
    for test in tests:
        passed_symbol = ' ✅' if test.id in passed_tests_ids else ''
        button_text = f"{test.test_name}{passed_symbol}"
        callback_data = f"view_results_test:{test.id}" if active else "noop"
        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=callback_data
            )
        ])

    navigation_buttons = []
    if page > 1:
        callback_data_prev = f"tests_page:{page - 1}" if active else "noop"
        navigation_buttons.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data_prev))
    if page < total_pages:
        callback_data_next = f"tests_page:{page + 1}" if active else "noop"
        navigation_buttons.append(
            InlineKeyboardButton(text="➡️ Вперёд", callback_data=callback_data_next))

    if navigation_buttons:
        buttons.append(navigation_buttons)

    # Добавляем кнопку "⬅️ Назад в главное меню"
    callback_data_back = "back_to_main_menu" if active else "noop"
    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data=callback_data_back)]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_attempts_keyboard(attempts: List[TestAttempt], page: int, total_pages: int, test_id: int,
                             max_score: int, active: bool = True) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с попытками и кнопками навигации.
    """
    buttons = []
    for attempt in attempts:
        try:
            # Обработка attempt.answers как dict или str
            if isinstance(attempt.answers, str):
                try:
                    answers_dict = json.loads(attempt.answers)
                except json.JSONDecodeError as e:
                    logger.error(f"Ошибка десериализации answers для попытки {attempt.id}: {e}")
                    answers_dict = {}
            elif isinstance(attempt.answers, dict):
                answers_dict = attempt.answers
            else:
                logger.error(
                    f"Ожидалась строка JSON или dict для attempt.answers, но получен тип: {type(attempt.answers)}")
                answers_dict = {}

            # Подсчет набранных баллов
            attempt_score = sum(1 for ans in answers_dict.values() if isinstance(ans, dict) and ans.get('correct'))
            logger.debug(f"Attempt ID={attempt.id}: Score={attempt_score}/{max_score}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при обработке attempt.answers для попытки {attempt.id}: {e}")
            attempt_score = 0

        attempt_date = attempt.start_time.strftime('%Y-%m-%d %H:%M')
        passed_symbol = '✅' if attempt.passed else '❌'
        button_text = f"Попытка от {attempt_date} - {attempt_score}/{max_score} - {passed_symbol}"

        callback_data = f"view_attempt:{attempt.id}" if active else "noop"
        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=callback_data
            )
        ])

    # Навигационные кнопки
    navigation_buttons = []
    if page > 1:
        callback_data_prev = f"attempts_page:{test_id}:{page - 1}" if active else "noop"
        navigation_buttons.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data_prev))
    if page < total_pages:
        callback_data_next = f"attempts_page:{test_id}:{page + 1}" if active else "noop"
        navigation_buttons.append(
            InlineKeyboardButton(text="➡️ Вперёд", callback_data=callback_data_next))

    if navigation_buttons:
        buttons.append(navigation_buttons)

    # Добавляем кнопку "⬅️ Назад к списку тестов"
    callback_data_back = "back_to_tests_menu" if active else "noop"
    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад к списку тестов", callback_data=callback_data_back)]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_attempt_details_keyboard(attempt_id: int, question_index: int, total_questions: int,
                                    active: bool = True) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для навигации по деталям попытки.
    Если active=False, кнопки будут неактивны.
    """
    navigation_buttons = []
    if question_index > 0:
        callback_data_prev = f"attempt_nav:{attempt_id}:{question_index - 1}" if active else "noop"
        navigation_buttons.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data_prev))
    if question_index < total_questions - 1:
        callback_data_next = f"attempt_nav:{attempt_id}:{question_index + 1}" if active else "noop"
        navigation_buttons.append(
            InlineKeyboardButton(text="➡️ Вперёд", callback_data=callback_data_next))

    # Добавляем кнопку "⬅️ Назад к списку попыток"
    callback_data_back = "back_to_attempts" if active else "noop"
    navigation_buttons.append(
        InlineKeyboardButton(text="⬅️ Назад к списку попыток", callback_data=callback_data_back)
    )

    return InlineKeyboardMarkup(inline_keyboard=[navigation_buttons])


@router.message(lambda message: message.text == "Пройденные тесты")
async def show_results_menu(message: types.Message, session: AsyncSession, state: FSMContext):
    logger.info(
        f"Обработчик 'Пройденные тесты' вызван для пользователя {message.from_user.username}")
    user_id = message.from_user.id

    # Проверяем, находится ли пользователь в состоянии тестирования
    user_testing = await is_user_testing(state)
    if user_testing:
        await message.answer(
            "Вы сейчас проходите тест. Пожалуйста, завершите текущий тест перед тем, как просматривать пройденные тесты.")
        return

    # Получение объекта пользователя
    user_result = await session.execute(select(User).where(User.user_id == user_id))
    user: Optional[User] = user_result.scalars().first()
    if not user:
        await message.answer("Пользователь не зарегистрирован в системе.")
        return

    # Получение всех попыток пользователя с предзагрузкой тестов
    result = await session.execute(
        select(TestAttempt)
        .options(selectinload(TestAttempt.test))
        .where(TestAttempt.user_id == user.id)
        .order_by(TestAttempt.start_time.desc())  # Сортировка по последней попытке
    )
    attempts = result.scalars().all()

    if not attempts:
        await message.answer("У вас пока нет попыток прохождения тестов.")
        return

    # Получение уникальных тестов в порядке последней попытки
    tests_dict = {}
    passed_tests_ids = set()
    for attempt in attempts:
        if attempt.test_id not in tests_dict:
            tests_dict[attempt.test_id] = attempt.test
        if attempt.passed:
            passed_tests_ids.add(attempt.test_id)

    tests = list(tests_dict.values())

    # Пагинация
    total_pages = (len(tests) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    current_page = 1

    paginated_tests = tests[:ITEMS_PER_PAGE]

    # Определяем активность кнопок
    active = not user_testing

    keyboard = create_tests_keyboard(
        paginated_tests, list(passed_tests_ids), current_page, total_pages, active=active)

    sent_message = await message.answer("Выберите тест для просмотра попыток:", reply_markup=keyboard)

    # Сохраняем message_id отправленного сообщения с тестами для последующего редактирования
    await state.update_data(tests_message_id=sent_message.message_id)
    await state.set_state(TestStates.VIEWING_TESTS)


@router.callback_query(StateFilter(TestStates.VIEWING_TESTS), lambda c: c.data and c.data.startswith("tests_page:"))
async def paginate_tests(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

    try:
        _, page_str = callback.data.split(":")
        page = int(page_str)
    except ValueError:
        await callback.message.answer("Некорректный номер страницы.")
        return

    user_id = callback.from_user.id

    # Проверяем, находится ли пользователь в состоянии тестирования
    user_testing = await is_user_testing(state)
    if user_testing:
        await callback.message.edit_text(
            "Вы сейчас проходите тест. Пожалуйста, завершите текущий тест перед тем, как просматривать пройденные тесты.")
        return

    # Получение объекта пользователя
    user_result = await session.execute(
        select(User).where(User.user_id == user_id)
    )
    user: Optional[User] = user_result.scalars().first()
    if not user:
        await callback.message.answer("Пользователь не зарегистрирован в системе.")
        return

    # Получение всех попыток пользователя с предзагрузкой тестов
    result = await session.execute(
        select(TestAttempt)
        .options(selectinload(TestAttempt.test))
        .where(TestAttempt.user_id == user.id)
        .order_by(TestAttempt.start_time.desc())
    )
    attempts = result.scalars().all()

    if not attempts:
        await callback.message.answer("У вас пока нет попыток прохождения тестов.")
        return

    # Получение уникальных тестов в порядке последней попытки
    tests_dict = {}
    passed_tests_ids = set()
    for attempt in attempts:
        if attempt.test_id not in tests_dict:
            tests_dict[attempt.test_id] = attempt.test
        if attempt.passed:
            passed_tests_ids.add(attempt.test_id)

    tests = list(tests_dict.values())

    # Пагинация
    total_pages = (len(tests) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    if page < 1 or page > total_pages:
        await callback.message.answer("Страница не найдена.")
        return

    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    paginated_tests = tests[start_index:end_index]

    # Определяем активность кнопок
    active = not user_testing

    keyboard = create_tests_keyboard(
        paginated_tests, list(passed_tests_ids), page, total_pages, active=active)

    await callback.message.edit_text(
        "Выберите тест для просмотра попыток:", reply_markup=keyboard)

    # Сохраняем обновленный message_id
    await state.update_data(tests_message_id=callback.message.message_id)
    await state.set_state(TestStates.VIEWING_TESTS)


@router.callback_query(StateFilter(TestStates.VIEWING_TESTS),
                       lambda c: c.data and c.data.startswith("view_results_test:"))
async def select_test(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

    user_id = callback.from_user.id

    # Проверяем, находится ли пользователь в состоянии тестирования
    user_testing = await is_user_testing(state)
    if user_testing:
        await callback.message.edit_text(
            "Вы сейчас проходите тест. Пожалуйста, завершите текущий тест перед тем, как просматривать пройденные тесты.")
        return

    try:
        _, test_id_str = callback.data.split(":")
        test_id = int(test_id_str)
    except ValueError:
        await callback.message.answer("Некорректный ID теста.")
        return

    # Получение объекта пользователя
    user_result = await session.execute(
        select(User).where(User.user_id == user_id)
    )
    user: Optional[User] = user_result.scalars().first()
    if not user:
        await callback.message.answer(
            "Пользователь не зарегистрирован в системе."
        )
        return

    # Получение попыток для выбранного теста
    result = await session.execute(
        select(TestAttempt)
        .where(TestAttempt.user_id == user.id, TestAttempt.test_id == test_id)
        .order_by(TestAttempt.start_time.desc())
    )
    attempts = result.scalars().all()

    if not attempts:
        await callback.message.answer(
            "У вас нет попыток для этого теста."
        )
        return

    # Загрузка теста с вопросами для получения максимального количества баллов
    test_result = await session.execute(
        select(Test)
        .options(selectinload(Test.questions))
        .where(Test.id == test_id)
    )
    test: Optional[Test] = test_result.scalars().first()
    if not test:
        await callback.message.answer("Тест не найден.")
        return

    # Максимальное количество баллов равно количеству вопросов
    max_score = len(test.questions)

    # Пагинация
    total_pages = (len(attempts) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    current_page = 1

    paginated_attempts = attempts[:ITEMS_PER_PAGE]

    # Определяем активность кнопок
    active = not user_testing

    keyboard = create_attempts_keyboard(
        paginated_attempts, current_page, total_pages, test_id, max_score, active=active
    )

    sent_message = await callback.message.edit_text(
        "Выберите попытку для просмотра результатов:", reply_markup=keyboard
    )
    await state.update_data(selected_test_id=test_id, max_score=max_score)
    await state.set_state(TestStates.VIEWING_ATTEMPTS)

    # Сохраняем message_id отправленного сообщения с попытками для последующего редактирования
    await state.update_data(attempts_message_id=sent_message.message_id)


@router.callback_query(StateFilter(TestStates.VIEWING_ATTEMPTS),
                       lambda c: c.data and c.data.startswith("attempts_page:"))
async def paginate_attempts(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

    try:
        _, test_id_str, page_str = callback.data.split(":")
        test_id = int(test_id_str)
        page = int(page_str)
    except ValueError:
        await callback.message.answer("Некорректные данные пагинации.")
        return

    user_id = callback.from_user.id

    # Проверяем, находится ли пользователь в состоянии тестирования
    user_testing = await is_user_testing(state)
    if user_testing:
        await callback.message.edit_text(
            "Вы сейчас проходите тест. Пожалуйста, завершите текущий тест перед тем, как просматривать пройденные тесты.")
        return

    # Получение объекта пользователя
    user_result = await session.execute(select(User).where(User.user_id == user_id))
    user: Optional[User] = user_result.scalars().first()
    if not user:
        await callback.message.answer("Пользователь не зарегистрирован в системе.")
        return

    # Получение попыток пользователя для выбранного теста
    result = await session.execute(
        select(TestAttempt)
        .where(TestAttempt.user_id == user.id, TestAttempt.test_id == test_id)
        .order_by(TestAttempt.start_time.desc())
    )
    attempts = result.scalars().all()

    if not attempts:
        await callback.message.answer("У вас нет попыток для этого теста.")
        return

    # Загрузка теста с вопросами для получения максимального количества баллов
    test_result = await session.execute(
        select(Test)
        .options(selectinload(Test.questions))
        .where(Test.id == test_id)
    )
    test: Optional[Test] = test_result.scalars().first()
    if not test:
        await callback.message.answer("Тест не найден.")
        return

    max_score = len(test.questions)

    # Пагинация
    total_pages = (len(attempts) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    if page < 1 or page > total_pages:
        await callback.message.answer("Страница не найдена.")
        return

    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    paginated_attempts = attempts[start_index:end_index]

    # Определяем активность кнопок
    active = not user_testing

    keyboard = create_attempts_keyboard(
        paginated_attempts, page, total_pages, test_id, max_score, active=active
    )

    await callback.message.edit_text(
        "Выберите попытку для просмотра результатов:", reply_markup=keyboard)
    await state.set_state(TestStates.VIEWING_ATTEMPTS)

    # Сохраняем обновленный message_id
    await state.update_data(attempts_message_id=callback.message.message_id)


@router.callback_query(StateFilter(TestStates.VIEWING_ATTEMPTS),
                       lambda c: c.data and c.data.startswith("view_attempt:"))
async def view_attempt(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

    user_id = callback.from_user.id

    # Проверяем, находится ли пользователь в состоянии тестирования
    user_testing = await is_user_testing(state)
    if user_testing:
        await callback.message.edit_text(
            "Вы сейчас проходите тест. Пожалуйста, завершите текущий тест перед тем, как просматривать пройденные тесты.")
        return

    try:
        _, attempt_id_str = callback.data.split(":")
        attempt_id = int(attempt_id_str)
    except ValueError:
        await callback.message.answer("Некорректный ID попытки.")
        return

    # Загрузка попытки с ответами
    result = await session.execute(
        select(TestAttempt)
        .options(
            selectinload(TestAttempt.test).selectinload(Test.questions)  # Загрузка теста и его вопросов
        )
        .where(TestAttempt.id == attempt_id)
    )
    attempt: Optional[TestAttempt] = result.scalars().first()

    if not attempt:
        await callback.message.answer("Попытка не найдена.")
        return

    # Получение вопросов из теста
    questions = attempt.test.questions

    if not questions:
        await callback.message.answer("Вопросы для этого теста не найдены.")
        return

    # Сохранение необходимых данных в состоянии
    if isinstance(attempt.answers, str):
        try:
            attempt_answers_dict = json.loads(attempt.answers)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка десериализации answers для попытки {attempt.id}: {e}")
            attempt_answers_dict = {}
    elif isinstance(attempt.answers, dict):
        attempt_answers_dict = attempt.answers
    else:
        logger.error(f"Ожидалась строка JSON или dict для attempt.answers, но получен тип: {type(attempt.answers)}")
        attempt_answers_dict = {}

    await state.update_data(
        attempt_id=attempt_id,
        questions=questions,
        question_index=0,
        attempt_answers=attempt_answers_dict  # Теперь это словарь
    )
    await state.set_state(TestStates.VIEWING_ATTEMPT_DETAILS)

    # Отправка первого вопроса
    await send_attempt_question(callback.message, state)


@router.callback_query(StateFilter(TestStates.VIEWING_ATTEMPT_DETAILS),
                       lambda c: c.data and c.data.startswith("attempt_nav:"))
async def navigate_attempt_questions(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    try:
        _, attempt_id_str, question_index_str = callback.data.split(":")
        attempt_id = int(attempt_id_str)
        question_index = int(question_index_str)
    except ValueError:
        await callback.message.answer("Некорректные данные навигации.")
        return

    # Проверяем, находится ли пользователь в состоянии тестирования
    user_testing = await is_user_testing(state)
    if user_testing:
        await callback.message.edit_text(
            "Вы сейчас проходите тест. Пожалуйста, завершите текущий тест перед тем, как просматривать пройденные тесты.")
        return

    await state.update_data(
        attempt_id=attempt_id,
        question_index=question_index
    )

    await send_attempt_question(callback.message, state)


async def send_attempt_question(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    attempt_id = user_data.get('attempt_id')
    questions: List[Question] = user_data.get('questions', [])
    question_index = user_data.get('question_index', 0)
    attempt_answers: Dict[str, Any] = user_data.get('attempt_answers', {})

    if question_index < 0 or question_index >= len(questions):
        await message.answer("Вопрос не найден.")
        return

    current_question: Question = questions[question_index]
    question_id_str = str(current_question.id)
    user_answer_entry = attempt_answers.get(question_id_str)
    is_correct = False

    if user_answer_entry is not None:
        is_correct = user_answer_entry.get('correct', False)
        user_answer = user_answer_entry.get('user_answer', None)
    else:
        user_answer = None
        is_correct = False

    # Обработка ответа пользователя для множественного выбора и single_choice
    if current_question.question_type == 'multiple_choice':
        if isinstance(user_answer, list):
            user_answer_list = [str(ans) for ans in user_answer]  # Убедимся, что все ответы - строки
        elif isinstance(user_answer, str):
            # Если ответы хранятся как строка, разбиваем их на список символов
            user_answer_list = list(user_answer)
        else:
            user_answer_list = []
    elif current_question.question_type == 'single_choice':
        if isinstance(user_answer, list) and len(user_answer) == 1:
            user_answer_list = [str(user_answer[0])]
        elif isinstance(user_answer, str):
            user_answer_list = [user_answer]
        else:
            user_answer_list = []
    else:
        user_answer_list = [str(user_answer)] if user_answer is not None else []

    # Построение текста сообщения
    question_text = f"Вопрос {question_index + 1}/{len(questions)}:\n\n{current_question.question_text}\n\n"

    if current_question.question_type in ['single_choice', 'multiple_choice']:
        if current_question.question_type == 'multiple_choice':
            question_text += f"Выберите один вариант ответа:\n"
        else:
            question_text += f"Выберите один или несколько вариантов ответа:\n"

        options_text = ""
        for idx, option in enumerate(current_question.options, start=1):
            option_id_str = str(option['id'])
            if current_question.question_type == 'single_choice':

                selected = (option_id_str == user_answer_list[0]) if user_answer_list else False
            elif current_question.question_type == 'multiple_choice':
                selected = (option_id_str in user_answer_list)
            else:
                selected = False

            checkmark = "✅" if selected else ""
            options_text += f"{idx}. {option['text']} {checkmark}\n"
        question_text += options_text
    elif current_question.question_type == 'text_input':
        if user_answer:
            question_text += f"Ваш ответ: {user_answer}\n"
        else:
            question_text += "Вы не ответили на этот вопрос.\n"

    # Обработка отсутствующего ответа
    if user_answer_entry is None:
        if current_question.question_type == 'text_input':
            question_text += f"\nРезультат: Не отвечено"
        else:
            question_text += f"\nРезультат: ❌ Неправильно"
    else:
        question_text += f"\nРезультат: {'✅ Правильно' if is_correct else '❌ Неправильно'}"

    # Создание клавиатуры
    keyboard = create_attempt_details_keyboard(
        attempt_id, question_index, len(questions), active=True
    )

    # Логирование для отладки
    logger.debug(f"Attempt ID: {attempt_id}, Question Index: {question_index}")
    logger.debug(f"Current Question ID: {current_question.id}")
    logger.debug(f"User Answer Entry: {user_answer_entry}")
    logger.debug(f"User Answer List: {user_answer_list}")
    logger.debug(f"Is Correct: {is_correct}")
    logger.debug(f"Question Text: {question_text}")

    try:
        await message.edit_text(question_text, reply_markup=keyboard)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            logger.debug("Message is not modified. Skipping edit.")
            pass
        else:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            await message.answer(question_text, reply_markup=keyboard)


@router.callback_query(StateFilter(TestStates.VIEWING_ATTEMPT_DETAILS), lambda c: c.data == "back_to_attempts")
async def back_to_attempts(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

    user_data = await state.get_data()
    test_id = user_data.get('selected_test_id')
    if not test_id:
        await callback.message.answer("Ошибка возврата к списку попыток.")
        return

    user_id = callback.from_user.id

    # Проверяем, находится ли пользователь в состоянии тестирования
    user_testing = await is_user_testing(state)
    if user_testing:
        await callback.message.edit_text(
            "Вы сейчас проходите тест. Пожалуйста, завершите текущий тест перед тем, как просматривать пройденные тесты.")
        return

    # Получение объекта пользователя
    user_result = await session.execute(
        select(User).where(User.user_id == user_id)
    )
    user: Optional[User] = user_result.scalars().first()
    if not user:
        await callback.message.answer("Пользователь не найден.")
        return

    # Получение попыток пользователя для выбранного теста
    result = await session.execute(
        select(TestAttempt)
        .where(TestAttempt.user_id == user.id, TestAttempt.test_id == test_id)
        .order_by(TestAttempt.start_time.desc())
    )
    attempts = result.scalars().all()

    if not attempts:
        await callback.message.answer("У вас нет попыток для этого теста.")
        return

    # Загрузка теста с вопросами для получения максимального количества баллов
    test_result = await session.execute(
        select(Test)
        .options(selectinload(Test.questions))
        .where(Test.id == test_id)
    )
    test: Optional[Test] = test_result.scalars().first()
    if not test:
        await callback.message.answer("Тест не найден.")
        return

    max_score = len(test.questions)

    # Пагинация
    total_pages = (len(attempts) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    current_page = 1

    paginated_attempts = attempts[:ITEMS_PER_PAGE]

    # Определяем активность кнопок
    active = not user_testing

    keyboard = create_attempts_keyboard(
        paginated_attempts, current_page, total_pages, test_id, max_score, active=active
    )

    sent_message = await callback.message.edit_text(
        "Выберите попытку для просмотра результатов:", reply_markup=keyboard)
    await state.set_state(TestStates.VIEWING_ATTEMPTS)

    # Сохраняем обновленный message_id
    await state.update_data(attempts_message_id=sent_message.message_id)


@router.callback_query(StateFilter(TestStates.VIEWING_ATTEMPTS), lambda c: c.data == "back_to_tests_menu")
async def back_to_tests_menu(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

    logger.debug("Handler 'back_to_tests_menu' triggered.")

    user_id = callback.from_user.id

    # Проверяем, находится ли пользователь в состоянии тестирования
    user_testing = await is_user_testing(state)
    if user_testing:
        await callback.message.edit_text(
            "Вы сейчас проходите тест. Пожалуйста, завершите текущий тест перед тем, как просматривать пройденные тесты.")
        return

    # Получение объекта пользователя
    user_result = await session.execute(
        select(User).where(User.user_id == user_id)
    )
    user: Optional[User] = user_result.scalars().first()
    if not user:
        await callback.message.answer("Пользователь не зарегистрирован в системе.")
        return

    # Получение всех попыток пользователя с предзагрузкой тестов
    result = await session.execute(
        select(TestAttempt)
        .options(selectinload(TestAttempt.test))
        .where(TestAttempt.user_id == user.id)
        .order_by(TestAttempt.start_time.desc())
    )
    attempts = result.scalars().all()

    if not attempts:
        await callback.message.answer("У вас пока нет попыток прохождения тестов.")
        return

    # Получение уникальных тестов в порядке последней попытки
    tests_dict = {}
    passed_tests_ids = set()
    for attempt in attempts:
        if attempt.test_id not in tests_dict:
            tests_dict[attempt.test_id] = attempt.test
        if attempt.passed:
            passed_tests_ids.add(attempt.test_id)

    tests = list(tests_dict.values())

    # Пагинация
    total_pages = (len(tests) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    current_page = 1

    paginated_tests = tests[:ITEMS_PER_PAGE]

    # Определяем активность кнопок
    active = not user_testing

    keyboard = create_tests_keyboard(
        paginated_tests, list(passed_tests_ids), current_page, total_pages, active=active)

    sent_message = await callback.message.edit_text("Выберите тест для просмотра попыток:", reply_markup=keyboard)

    # Сохраняем message_id отправленного сообщения с тестами для последующего редактирования
    await state.update_data(tests_message_id=sent_message.message_id)
    await state.set_state(TestStates.VIEWING_TESTS)


@router.callback_query(lambda c: c.data == "back_to_main_menu")
async def back_to_main_menu(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

    user_id = callback.from_user.id

    # Проверяем, находится ли пользователь в состоянии тестирования
    user_testing = await is_user_testing(state)
    if user_testing:
        await callback.message.edit_text(
            "Вы сейчас проходите тест. Пожалуйста, завершите текущий тест перед тем, как просматривать пройденные тесты.")
        return

    # Получение объекта пользователя
    user_result = await session.execute(
        select(User).where(User.user_id == user_id))
    user: Optional[User] = user_result.scalars().first()

    if not user:
        await callback.message.answer(
            "Вы не зарегистрированы. Пожалуйста, используйте команду /start для регистрации.")
        return

    # Отправка главного меню как нового сообщения с InlineKeyboardMarkup

    try:
        await callback.message.delete()  # Удаляем предыдущее сообщение
    except TelegramBadRequest:
        logger.warning("Предыдущее сообщение не удалось удалить.")
    await callback.message.answer(
        f"Добро пожаловать обратно, {user.firstname}!",
        reply_markup=get_main_menu(user.username, True)
    )
    await state.clear()


@router.callback_query(lambda c: c.data == "noop")
async def noop_handler(callback: types.CallbackQuery):
    await callback.answer()


async def send_attempt_question(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    attempt_id = user_data.get('attempt_id')
    questions: List[Question] = user_data.get('questions', [])
    question_index = user_data.get('question_index', 0)
    attempt_answers: Dict[str, Any] = user_data.get('attempt_answers', {})

    if question_index < 0 or question_index >= len(questions):
        await message.answer("Вопрос не найден.")
        return

    current_question: Question = questions[question_index]
    question_id_str = str(current_question.id)
    user_answer_entry = attempt_answers.get(question_id_str)
    is_correct = False

    if user_answer_entry is not None:
        is_correct = user_answer_entry.get('correct', False)
        user_answer = user_answer_entry.get('user_answer', None)
    else:
        user_answer = None
        is_correct = False

    # Обработка ответа пользователя для множественного выбора и single_choice
    if current_question.question_type == 'multiple_choice':
        if isinstance(user_answer, list):
            user_answer_list = [str(ans) for ans in user_answer]  # Убедимся, что все ответы - строки
        elif isinstance(user_answer, str):
            # Если ответы хранятся как строка, разбиваем их на список символов
            user_answer_list = list(user_answer)
        else:
            user_answer_list = []
    elif current_question.question_type == 'single_choice':
        if isinstance(user_answer, list) and len(user_answer) == 1:
            user_answer_list = [str(user_answer[0])]
        elif isinstance(user_answer, str):
            user_answer_list = [user_answer]
        else:
            user_answer_list = []
    else:
        user_answer_list = [str(user_answer)] if user_answer is not None else []

    # Построение текста сообщения
    question_text = f"Вопрос {question_index + 1}/{len(questions)}:\n\n{current_question.question_text}\n\n"

    if current_question.question_type in ['single_choice', 'multiple_choice']:
        options_text = ""
        for idx, option in enumerate(current_question.options, start=1):
            option_id_str = str(option['id'])
            if current_question.question_type == 'single_choice':
                selected = (option_id_str == user_answer_list[0]) if user_answer_list else False
            elif current_question.question_type == 'multiple_choice':
                selected = (option_id_str in user_answer_list)
            else:
                selected = False

            checkmark = "✅" if selected else ""
            options_text += f"{idx}. {option['text']} {checkmark}\n"
        question_text += options_text
    elif current_question.question_type == 'text_input':
        if user_answer:
            question_text += f"Ваш ответ: {user_answer}\n"
        else:
            question_text += "Вы не ответили на этот вопрос.\n"

    # Обработка отсутствующего ответа
    if user_answer_entry is None:
        if current_question.question_type == 'text_input':
            question_text += f"\nРезультат: Не отвечено"
        else:
            question_text += f"\nРезультат: ❌ Неправильно"
    else:
        question_text += f"\nРезультат: {'✅ Правильно' if is_correct else '❌ Неправильно'}"

    # Создание клавиатуры
    keyboard = create_attempt_details_keyboard(
        attempt_id, question_index, len(questions), active=True
    )

    # Логирование для отладки
    logger.debug(f"Attempt ID: {attempt_id}, Question Index: {question_index}")
    logger.debug(f"Current Question ID: {current_question.id}")
    logger.debug(f"User Answer Entry: {user_answer_entry}")
    logger.debug(f"User Answer List: {user_answer_list}")
    logger.debug(f"Is Correct: {is_correct}")
    logger.debug(f"Question Text: {question_text}")

    try:
        await message.edit_text(question_text, reply_markup=keyboard)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            logger.debug("Message is not modified. Skipping edit.")
            pass
        else:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            await message.answer(question_text, reply_markup=keyboard)
