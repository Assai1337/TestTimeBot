# handlers/main_menu.py
from typing import List
from zoneinfo import ZoneInfo
import re
from datetime import datetime
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from tools.models import User, Group, Test, TestAttempt
from tools.config import ADMIN_USERNAME
import logging

router = Router()

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Состояния для FSM
class Registration(StatesGroup):
    awaiting_user_data = State()

# Функция для создания главного меню
def get_main_menu(username: str) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="Доступные тесты")],
        [KeyboardButton(text="Пройденные тесты")]
    ]
    if username == ADMIN_USERNAME:
        buttons.append([KeyboardButton(text="Админ панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# Обработчик команды /start
@router.message(Command(commands="start"))
async def start_handler(message: types.Message, state: FSMContext, session: AsyncSession):
    username = message.from_user.username
    logger.info(f"Получено сообщение /start от пользователя {username}")  # Отладочный вывод

    if not username:
        await message.reply("Ваш профиль Telegram не содержит имени пользователя (username). Регистрация невозможна.")
        return

    try:
        # Проверяем пользователя в базе данных
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalars().first()

        if user:
            await message.reply(
                f"Добро пожаловать обратно, {user.firstname}!",
                reply_markup=get_main_menu(username)
            )
        else:
            await message.reply(
                "Вы новый пользователь. Пожалуйста, введите свои данные в формате:\n"
                "Фамилия Имя Отчество Группа\nПример: Иванов Иван Иванович Б121"
            )
            await state.set_state(Registration.awaiting_user_data)
    except Exception as e:
        logger.error(f"Ошибка в обработчике /start: {e}")
        await message.reply("Произошла ошибка при проверке данных. Попробуйте позже.")

# Обработчик регистрации нового пользователя
@router.message(Registration.awaiting_user_data)
async def register_new_user(message: types.Message, state: FSMContext, session: AsyncSession):
    user_data = message.text.split()
    if len(user_data) != 4:
        await message.reply(
            "Пожалуйста, введите данные в формате:\nФамилия Имя Отчество Группа\n"
            "Пример: Иванов Иван Иванович Б121"
        )
        return

    last_name, first_name, middle_name, group_name = map(str.strip, user_data)
    username = message.from_user.username

    if not re.match(r"^[А-Яа-я0-9]+$", group_name):
        await message.reply(
            "Поле 'группа' может содержать только русские буквы и цифры.\nПример: Б121."
        )
        return

    try:
        # Проверяем, существует ли группа
        result = await session.execute(select(Group).where(Group.groupname == group_name))
        group = result.scalars().first()
        if not group:
            group = Group(groupname=group_name)
            session.add(group)

        # Проверяем, существует ли пользователь
        result = await session.execute(select(User).where(User.username == username))
        existing_user = result.scalars().first()
        if existing_user:
            await message.reply("Вы уже зарегистрированы.", reply_markup=get_main_menu(username))
            await state.clear()
            return

        # Создаем нового пользователя
        new_user = User(
            user_id=message.from_user.id,
            username=username,
            firstname=first_name.capitalize(),
            middlename=middle_name.capitalize(),
            lastname=last_name.capitalize(),
            group=group_name,
            registration_date=datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
        )
        session.add(new_user)
        await session.commit()

        await message.reply(
            f"Регистрация завершена! Добро пожаловать, {first_name.capitalize()}.",
            reply_markup=get_main_menu(username)
        )
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка при регистрации: {e}")
        await message.reply("Произошла ошибка при регистрации. Попробуйте позже.")

# Обработчик кнопки "Админ панель"
@router.message(lambda message: message.text == "Админ панель")
async def admin_panel_handler(message: types.Message):
    if message.from_user.username == ADMIN_USERNAME:
        await message.answer(
            "Добро пожаловать в админ панель!\n"
            "[Открыть админ панель](http://localhost:5000/admin)",
            parse_mode="Markdown"
        )
    else:
        await message.answer("У вас нет доступа к админ панели.")

# Обработчик кнопки "Доступные тесты"
@router.message(lambda message: message.text == "Доступные тесты")
async def available_tests_handler(message: types.Message, session: AsyncSession):
    logger.info("Обработчик 'Доступные тесты' вызван")

    try:
        # Получаем пользователя
        user_result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = user_result.scalars().first()

        if not user:
            await message.answer("Вы не зарегистрированы. Пожалуйста, используйте команду /start для регистрации.")
            return

        logger.info(f"Пользователь: {user.firstname} {user.lastname}, Группа: {user.group}")

        # Текущая дата и время
        current_time = datetime.utcnow()

        # Подготовка запроса с подсчетом попыток
        stmt = (
            select(Test, func.count(TestAttempt.id).label("attempt_count"))
            .outerjoin(TestAttempt, (Test.id == TestAttempt.test_id) & (TestAttempt.user_id == user.id))
            .where(
                (Test.expiry_date == None) | (Test.expiry_date > current_time),
                Test.question_count > 0
            )
            .group_by(Test.id)
            .having(func.count(TestAttempt.id) < Test.number_of_attempts)
        )

        # Выполнение запроса
        test_result = await session.execute(stmt)
        tests_with_attempts = test_result.all()  # Каждый элемент: (Test, attempt_count)

        logger.info(f"Найдено тестов после фильтрации по попыткам: {len(tests_with_attempts)}")

        # Фильтруем тесты по группе
        available_tests: List[Tuple[Test, int]] = []
        for test, attempt_count in tests_with_attempts:
            if not test.groups_with_access:
                # Если доступен для всех групп
                available_tests.append((test, test.number_of_attempts - attempt_count))
            else:
                # Проверяем, принадлежит ли пользователь к разрешенной группе
                allowed_groups = [group.strip() for group in test.groups_with_access.split(",")]
                if user.group in allowed_groups:
                    available_tests.append((test, test.number_of_attempts - attempt_count))

        logger.info(f"Доступных тестов для пользователя после фильтрации по группам: {len(available_tests)}")

        if not available_tests:
            await message.answer("Нет доступных тестов для вашей группы или вы исчерпали все попытки.")
            return

        # Генерация Inline-кнопок
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"{test.test_name} (до {test.expiry_date.strftime('%d.%m.%Y %H:%M') if test.expiry_date else '∞'}) (Попытки осталось: {remaining})",
                        callback_data=f"select_test:{test.id}"
                    )
                ] for test, remaining in available_tests
            ]
        )

        await message.answer("Выберите тест для прохождения:", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка в обработчике 'Доступные тесты': {e}")
        await message.answer("Произошла ошибка при получении тестов. Попробуйте позже.")
