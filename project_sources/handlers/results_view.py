from typing import Optional, List, Dict, Any
from aiogram import Router, types
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
logger.addHandler(handler)

ITEMS_PER_PAGE = 8  # Количество элементов на странице


def create_tests_keyboard(tests: List[Test], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с тестами и кнопками навигации.
    """
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{test.test_name}",
                callback_data=f"view_results_test:{test.id}"
            )
        ] for test in tests
    ]

    navigation_buttons = []
    if page > 1:
        navigation_buttons.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"tests_page:{page - 1}"))
    if page < total_pages:
        navigation_buttons.append(
            InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"tests_page:{page + 1}"))

    if navigation_buttons:
        buttons.append(navigation_buttons)

    # Добавляем кнопку "⬅️ Назад в главное меню"
    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_attempts_keyboard(attempts: List[TestAttempt], page: int, total_pages: int, test_id: int, max_score: int) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с попытками и кнопками навигации.
    """
    buttons = []
    for attempt in attempts:
        # Подсчет набранных баллов
        attempt_score = sum(1 for ans in attempt.answers.values() if ans.get('correct'))
        attempt_date = attempt.start_time.strftime('%Y-%m-%d %H:%M')
        passed_symbol = '✅' if attempt.passed else '❌'
        button_text = f"Попытка от {attempt_date} - {attempt_score}/{max_score} - {passed_symbol}"

        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"view_attempt:{attempt.id}"
            )
        ])

    navigation_buttons = []
    if page > 1:
        navigation_buttons.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"attempts_page:{test_id}:{page - 1}"))
    if page < total_pages:
        navigation_buttons.append(
            InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"attempts_page:{test_id}:{page + 1}"))

    if navigation_buttons:
        buttons.append(navigation_buttons)

    # Добавляем кнопку "⬅️ Назад к списку тестов"
    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад к списку тестов", callback_data="back_to_tests_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_attempt_details_keyboard(attempt_id: int, question_index: int, total_questions: int) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для навигации по деталям попытки.
    """
    navigation_buttons = []
    if question_index > 0:
        navigation_buttons.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"attempt_nav:{attempt_id}:{question_index - 1}"))
    if question_index < total_questions - 1:
        navigation_buttons.append(
            InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"attempt_nav:{attempt_id}:{question_index + 1}"))

    # Добавляем кнопку "⬅️ Назад к списку попыток"
    navigation_buttons.append(
        InlineKeyboardButton(text="⬅️ Назад к списку попыток", callback_data="back_to_attempts"))

    return InlineKeyboardMarkup(inline_keyboard=[navigation_buttons])


@router.message(lambda message: message.text == "Пройденные тесты")
async def show_results_menu(message: types.Message, session: AsyncSession, state: FSMContext):
    logger.info(
        f"Обработчик 'Пройденные тесты' вызван для пользователя {message.from_user.username}")
    user_id = message.from_user.id

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
    for attempt in attempts:
        if attempt.test_id not in tests_dict:
            tests_dict[attempt.test_id] = attempt.test

    tests = list(tests_dict.values())

    # Пагинация
    total_pages = (len(tests) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    current_page = 1

    paginated_tests = tests[:ITEMS_PER_PAGE]

    keyboard = create_tests_keyboard(
        paginated_tests, current_page, total_pages)

    await message.answer("Выберите тест для просмотра попыток:", reply_markup=keyboard)
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

    # Получение объекта пользователя
    user_result = await session.execute(
        select(User).where(User.user_id == user_id))
    user: Optional[User] = user_result.scalars().first()
    if not user:
        await callback.message.answer(
            "Пользователь не зарегистрирован в системе.")
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
        await callback.message.answer(
            "У вас пока нет попыток прохождения тестов.")
        return

    # Получение уникальных тестов в порядке последней попытки
    tests_dict = {}
    for attempt in attempts:
        if attempt.test_id not in tests_dict:
            tests_dict[attempt.test_id] = attempt.test

    tests = list(tests_dict.values())

    # Пагинация
    total_pages = (len(tests) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    if page < 1 or page > total_pages:
        await callback.message.answer("Страница не найдена.")
        return

    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    paginated_tests = tests[start_index:end_index]

    keyboard = create_tests_keyboard(paginated_tests, page, total_pages)

    await callback.message.edit_text(
        "Выберите тест для просмотра попыток:", reply_markup=keyboard)
    await state.set_state(TestStates.VIEWING_TESTS)


@router.callback_query(StateFilter(TestStates.VIEWING_TESTS), lambda c: c.data and c.data.startswith("view_results_test:"))
async def select_test(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

    try:
        _, test_id_str = callback.data.split(":")
        test_id = int(test_id_str)
    except ValueError:
        await callback.message.answer("Некорректный ID теста.")
        return

    user_id = callback.from_user.id

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

    keyboard = create_attempts_keyboard(
        paginated_attempts, current_page, total_pages, test_id, max_score
    )

    await callback.message.edit_text(
        "Выберите попытку для просмотра результатов:", reply_markup=keyboard
    )
    await state.update_data(selected_test_id=test_id, max_score=max_score)
    await state.set_state(TestStates.VIEWING_ATTEMPTS)


@router.callback_query(StateFilter(TestStates.VIEWING_ATTEMPTS), lambda c: c.data and c.data.startswith("attempts_page:"))
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

    max_score = len(test.questions)

    total_pages = (len(attempts) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    if page < 1 or page > total_pages:
        await callback.message.answer("Страница не найдена.")
        return

    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    paginated_attempts = attempts[start_index:end_index]

    keyboard = create_attempts_keyboard(
        paginated_attempts, page, total_pages, test_id, max_score
    )

    await callback.message.edit_text(
        "Выберите попытку для просмотра результатов:", reply_markup=keyboard
    )
    await state.update_data(selected_test_id=test_id, max_score=max_score)
    await state.set_state(TestStates.VIEWING_ATTEMPTS)


@router.callback_query(StateFilter(TestStates.VIEWING_ATTEMPTS), lambda c: c.data and c.data.startswith("view_attempt:"))
async def view_attempt(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

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
    await state.update_data(
        attempt_id=attempt_id,
        questions=questions,
        question_index=0,
        attempt_answers=attempt.answers  # Должен быть словарь с ID вопросов в качестве ключей
    )
    await state.set_state(TestStates.VIEWING_ATTEMPT_DETAILS)

    # Отправка первого вопроса
    await send_attempt_question(callback.message, state)


@router.callback_query(StateFilter(TestStates.VIEWING_ATTEMPT_DETAILS), lambda c: c.data and c.data.startswith("attempt_nav:"))
async def navigate_attempt_questions(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    try:
        _, attempt_id_str, question_index_str = callback.data.split(":")
        attempt_id = int(attempt_id_str)
        question_index = int(question_index_str)
    except ValueError:
        await callback.message.answer("Некорректные данные навигации.")
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
        user_answer = user_answer_entry.get('user_answer')
        is_correct = user_answer_entry.get('correct', False)
    else:
        user_answer = None
        is_correct = False

    # Обработка ответа пользователя для множественного выбора
    if current_question.question_type == 'multiple_choice' and isinstance(user_answer, str):
        user_answer_list = []
        remaining_answer = user_answer
        # Получаем список всех возможных идентификаторов вариантов
        option_ids = [str(option['id']) for option in current_question.options]
        # Сортируем по длине идентификаторов в обратном порядке
        option_ids.sort(key=lambda x: -len(x))
        for option_id in option_ids:
            count = remaining_answer.count(option_id)
            while option_id in remaining_answer:
                user_answer_list.append(option_id)
                # Удаляем найденный идентификатор из оставшейся строки
                remaining_answer = remaining_answer.replace(option_id, '', 1)
    else:
        user_answer_list = user_answer

    # Построение текста сообщения
    question_text = f"Вопрос {question_index + 1}/{len(questions)}:\n\n{current_question.question_text}\n\n"

    if current_question.question_type in ['single_choice', 'multiple_choice']:
        options_text = ""
        for idx, option in enumerate(current_question.options, start=1):
            option_id_str = str(option['id'])
            selected = False
            if user_answer_list:
                if current_question.question_type == 'single_choice':
                    selected = option_id_str == str(user_answer_list)
                elif current_question.question_type == 'multiple_choice':
                    selected = option_id_str in user_answer_list
            options_text += f"{idx}. {option['text']}{' ✅' if selected else ''}\n"
        question_text += options_text
    elif current_question.question_type == 'text_input':
        if user_answer:
            question_text += f"Ваш ответ: {user_answer}\n"
        else:
            question_text += "Вы не ответили на этот вопрос.\n"

    question_text += f"\nРезультат: {'✅ Правильно' if is_correct else '❌ Неправильно'}"

    # Создание клавиатуры
    keyboard = create_attempt_details_keyboard(
        attempt_id, question_index, len(questions))

    await message.edit_text(question_text, reply_markup=keyboard)



@router.callback_query(StateFilter(TestStates.VIEWING_ATTEMPT_DETAILS), lambda c: c.data == "back_to_attempts")
async def back_to_attempts(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

    user_data = await state.get_data()
    test_id = user_data.get('selected_test_id')
    if not test_id:
        await callback.message.answer("Ошибка возврата к списку попыток.")
        return

    # Получение попыток для теста
    user_id = callback.from_user.id

    user_result = await session.execute(
        select(User).where(User.user_id == user_id)
    )
    user: Optional[User] = user_result.scalars().first()
    if not user:
        await callback.message.answer("Пользователь не найден.")
        return

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

    keyboard = create_attempts_keyboard(
        paginated_attempts, current_page, total_pages, test_id, max_score
    )

    await callback.message.edit_text(
        "Выберите попытку для просмотра результатов:", reply_markup=keyboard)
    await state.set_state(TestStates.VIEWING_ATTEMPTS)


@router.callback_query(StateFilter(TestStates.VIEWING_ATTEMPTS), lambda c: c.data == "back_to_tests_menu")
async def back_to_tests_menu(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

    user_id = callback.from_user.id

    # Получение объекта пользователя
    user_result = await session.execute(select(User).where(User.user_id == user_id))
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
    for attempt in attempts:
        if attempt.test_id not in tests_dict:
            tests_dict[attempt.test_id] = attempt.test

    tests = list(tests_dict.values())

    # Пагинация
    total_pages = (len(tests) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    current_page = 1

    paginated_tests = tests[:ITEMS_PER_PAGE]

    keyboard = create_tests_keyboard(paginated_tests, current_page, total_pages)

    await callback.message.edit_text("Выберите тест для просмотра попыток:", reply_markup=keyboard)
    await state.set_state(TestStates.VIEWING_TESTS)


@router.callback_query(lambda c: c.data == "back_to_main_menu")
async def back_to_main_menu(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()

    user_id = callback.from_user.id

    # Получение объекта пользователя
    user_result = await session.execute(
        select(User).where(User.user_id == user_id))
    user: Optional[User] = user_result.scalars().first()

    if not user:
        await callback.message.answer(
            "Вы не зарегистрированы. Пожалуйста, используйте команду /start для регистрации.")
        return

    # Отправка главного меню как нового сообщения с ReplyKeyboardMarkup
    main_menu = get_main_menu(user.username)
    await callback.message.delete()  # Удаляем предыдущее сообщение
    await callback.message.answer(
        f"Добро пожаловать обратно, {user.firstname}!",
        reply_markup=main_menu
    )
    await state.clear()

