# test_passing.py

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo
from tools.config import ADMIN_CHAT_ID, DATABASE_URL
from aiogram import Router, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from .main_menu import get_main_menu
from tools.models import Test, Question, TestAttempt, User
import logging
from aiogram.exceptions import TelegramBadRequest

from tools.states import TestStates
from utils.decorators import check_active_test
from utils.calculate_score import calculate_score

import asyncio

router = Router()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def current_time():
    return datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)

async def notify_admin(bot: Bot, message: str):
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=message)
        except Exception as e:
            logger.error(f"Не удалось уведомить администратора: {e}")

# Функция для экранирования символов MarkdownV2
def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    for ch in escape_chars:
        text = text.replace(ch, f"\\{ch}")
    return text

async def monitor_test_time(user_id: int, test_attempt_id: int, end_time: datetime, bot: Bot, state: FSMContext):
    logger.debug(f"monitor_test_time started for user {user_id}, test_attempt {test_attempt_id}, end_time {end_time}")
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    now = current_time()
    delay = (end_time - now).total_seconds()
    logger.debug(f"Computed delay: {delay} seconds")
    if delay > 0:
        await asyncio.sleep(delay)
    else:
        delay = 0

    state_data = await state.get_data()
    current_state = await state.get_state()
    logger.debug(f"After sleep: state_data={state_data}, current_state={current_state}")

    if state_data.get('test_attempt_id') == test_attempt_id and current_state in [TestStates.TESTING.state, TestStates.EDITING.state]:
        logger.debug(f"Time expired. Attempt {test_attempt_id} finishing test for user {user_id}")

        # При окончании времени записываем ответы в БД один раз
        answers = state_data.get('answers', {})
        test_id = state_data.get('test_id')

        async with async_session() as session:
            test_attempt_result = await session.execute(
                select(TestAttempt).where(TestAttempt.id == test_attempt_id)
            )
            test_attempt: Optional[TestAttempt] = test_attempt_result.scalars().first()

            if not test_attempt:
                logger.error("TestAttempt not found in monitor_test_time")
                return

            test_result = await session.execute(
                select(Test).where(Test.id == test_attempt.test_id))
            test: Optional[Test] = test_result.scalars().first()
            if not test:
                logger.error(
                    f"Тест с ID {test_attempt.test_id} не найден при мониторинге времени.")
                return

            questions = state_data.get('questions', [])  # Уже загружено при start_test

            # Записываем ответы пользователя в test_attempt (один раз)
            test_attempt.answers = answers

            score, passed, detailed_answers = calculate_score(
                test, answers, questions)

            test_attempt.score = score
            test_attempt.passed = passed
            test_attempt.end_time = current_time()
            test_attempt.answers = detailed_answers

            user_result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user: Optional[User] = user_result.scalars().first()
            if not user:
                logger.error(f"Пользователь с ID {user_id} не найден при мониторинге времени.")
                return

            try:
                await session.commit()
                text_to_send = f"⏰ Время теста истекло. Ваш тест завершён.\n\nБаллы: {score}\nСтатус: {'✅ Пройден' if passed else '❌ Не пройден'}"
                text_to_send = escape_markdown_v2(text_to_send)
                await bot.send_message(
                    chat_id=user_id,
                    text=text_to_send,
                    parse_mode='MarkdownV2'
                )
                logger.info(
                    f"Автоматически завершён тест {test.id} для пользователя {user_id} (score={score}, passed={passed}).")

                await state.clear()
                logger.debug(f"State cleared for user {user_id} after auto-finishing test.")

                main_menu = get_main_menu(user.username, True)
                menu_text = "Вы можете выбрать следующий тест или воспользоваться другими опциями."
                menu_text = escape_markdown_v2(menu_text)
                await bot.send_message(
                    chat_id=user_id,
                    text=menu_text,
                    reply_markup=main_menu,
                    parse_mode='MarkdownV2'
                )
                logger.debug("Main menu sent after auto-finishing test.")
            except Exception as e:
                await session.rollback()
                logger.error(f"Ошибка при автоматическом завершении теста: {e}")
                await notify_admin(
                    bot, f"Ошибка при автоматическом завершении теста: {e}"
                )
    else:
        logger.debug("No conditions met for auto-finishing test.")

@router.callback_query(lambda c: c.data and c.data.startswith("select_test:"))
async def start_test(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    await callback.answer()
    current_state = await state.get_state()
    logger.debug(f"start_test: current_state={current_state}")

    if current_state == TestStates.TESTING.state:
        await callback.message.edit_text(
            "Вы уже проходите тест. Пожалуйста, завершите текущий тест перед началом нового."
        )
        return

    test_id_str = callback.data.split(":")[1]
    if not test_id_str.isdigit():
        await callback.message.answer("Некорректный ID теста.")
        return

    test_id = int(test_id_str)
    test_result = await session.execute(select(Test).where(Test.id == test_id))
    test: Optional[Test] = test_result.scalars().first()
    if not test:
        await callback.message.answer("Тест не найден.")
        return

    # Заранее грузим все вопросы и храним их в user_data
    question_result = await session.execute(
        select(Question).where(Question.test_id == test_id))
    questions = question_result.scalars().all()

    if not questions:
        await callback.message.answer("В этом тесте пока нет вопросов.")
        return

    start_time = current_time()
    end_time = start_time + timedelta(minutes=test.duration)
    user_id = callback.from_user.id

    user_result = await session.execute(
        select(User).where(User.user_id == user_id))
    user: Optional[User] = user_result.scalars().first()
    if not user:
        await callback.message.answer("Пользователь не найден в системе.")
        return

    test_attempt = TestAttempt(
        test_id=test_id,
        user_id=user.id,
        start_time=start_time,
        end_time=end_time,
        score=0,
        passed=False,
        answers={}
    )

    # Один раз создаём test_attempt
    try:
        session.add(test_attempt)
        await session.commit()
        logger.debug(f"Created TestAttempt ID={test_attempt.id} for user={user_id}, test={test_id}")
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка при создании попытки теста: {e}")
        await callback.message.answer("Произошла ошибка при создании попытки теста. Попробуйте позже.")
        await notify_admin(bot, f"Ошибка при создании попытки теста: {e}")
        return

    # Сохраняем все данные в user_data
    await state.update_data(
        test_id=test_id,
        test_attempt_id=test_attempt.id,
        questions=questions,
        current_index=0,
        start_time=start_time,
        end_time=end_time,
        answers={},
        message_id=callback.message.message_id
    )
    await state.set_state(TestStates.TESTING.state)
    logger.debug("State set to TESTING after start_test")

    await send_question(callback.message, state)
    asyncio.create_task(
        monitor_test_time(
            user_id=user_id,
            test_attempt_id=test_attempt.id,
            end_time=end_time,
            bot=bot,
            state=state
        )
    )


@router.callback_query(lambda c: c.data and c.data.startswith("answer:"))
@check_active_test
async def handle_answer(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    user_data = await state.get_data()
    logger.debug(f"handle_answer: user_data={user_data}")

    current_index = user_data["current_index"]
    questions: List[Question] = user_data["questions"]
    current_question: Question = questions[current_index]

    answer_id_str = callback.data.split(":")[1]
    if not answer_id_str.isdigit():
        await callback.message.answer("Некорректный ID ответа.")
        return

    answer_id = int(answer_id_str)
    answers = user_data.get("answers", {})

    # Никаких запросов к БД здесь не делаем, просто обновляем answers в памяти
    if current_question.question_type == "single_choice":
        current_selected = answers.get(str(current_question.id))
        if current_selected == answer_id_str:
            answers.pop(str(current_question.id), None)
        else:
            answers[str(current_question.id)] = answer_id_str
    elif current_question.question_type == "multiple_choice":
        current_answer = answers.get(str(current_question.id), "")
        if answer_id_str in current_answer:
            current_answer = current_answer.replace(answer_id_str, "")
        else:
            current_answer += answer_id_str
        answers[str(current_question.id)] = ''.join(sorted(current_answer))
    else:
        await callback.message.answer("Неподдерживаемый тип вопроса.")
        return

    # Сохраняем только в памяти (FSM), без коммита в БД
    await state.update_data(answers=answers)
    logger.debug(f"handle_answer: updated answers={answers}")

    logger.debug("Calling send_question from handle_answer")
    await send_question(callback.message, state)


@router.callback_query(lambda c: c.data and c.data.startswith("navigate:"))
@check_active_test
async def navigate_question(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_data = await state.get_data()
    logger.debug(f"navigate_question: user_data={user_data}")

    action = callback.data.split(":")[1]
    current_index = user_data["current_index"]
    questions: List[Question] = user_data["questions"]

    if action == "next" and current_index < len(questions) - 1:
        current_index += 1
    elif action == "prev" and current_index > 0:
        current_index -= 1
    else:
        await callback.message.answer("Невозможно выполнить это действие.")
        return

    await state.update_data(current_index=current_index)
    logger.debug(f"navigate_question: current_index={current_index}, calling send_question")
    await send_question(callback.message, state)


@router.callback_query(lambda c: c.data and c.data.startswith("edit_answer:"))
@check_active_test
async def edit_answer(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    user_data = await state.get_data()
    current_index = user_data.get("current_index", 0)
    questions = user_data.get("questions", [])
    logger.debug(f"edit_answer: user_data={user_data}")

    if not questions or current_index >= len(questions):
        await callback.message.answer("Вопрос не найден.")
        return

    current_question = questions[current_index]
    if current_question.question_type != "text_input":
        await callback.message.answer("Этот вопрос не поддерживает текстовый ввод.")
        return

    await state.set_state(TestStates.EDITING)
    logger.debug("State changed to EDITING in edit_answer")
    await state.update_data(editing_question_id=current_question.id)

    logger.debug("Calling send_question from edit_answer")
    await send_question(callback.message, state)


@router.message(TestStates.EDITING)
async def handle_text_edit(message: types.Message, state: FSMContext, session: AsyncSession):
    user_data = await state.get_data()
    logger.debug(f"handle_text_edit: user_data={user_data}")

    editing_question_id = user_data.get("editing_question_id")

    if not editing_question_id:
        await message.answer("Нет вопроса для редактирования.")
        return

    answers = user_data.get("answers", {})
    new_answer = message.text.strip()
    answers[str(editing_question_id)] = new_answer
    await state.update_data(answers=answers)
    logger.debug(f"handle_text_edit: new_answer={new_answer}, answers={answers}")

    # Не делаем коммит в БД сейчас, только в конце теста
    await state.set_state(TestStates.TESTING)
    logger.debug("State changed to TESTING in handle_text_edit after saving answer in memory")

    # Удаляем сообщение пользователя после обработки
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения пользователя: {e}")

    logger.debug("Calling send_question from handle_text_edit")
    await send_question(message, state)


@router.callback_query(lambda c: c.data == "finish_test")
@check_active_test
async def initiate_finish_test(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_data = await state.get_data()
    logger.debug(f"initiate_finish_test: user_data={user_data}")

    await state.set_state(TestStates.CONFIRM_FINISH.state)
    logger.debug("State changed to CONFIRM_FINISH in initiate_finish_test")

    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data="confirm_finish_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data="confirm_finish_no")
        ]
    ])

    confirmation_msg = await callback.message.answer(
        "Вы уверены, что хотите завершить тестирование?",
        reply_markup=confirm_keyboard
    )
    await state.update_data(confirmation_message_id=confirmation_msg.message_id)


@router.callback_query(lambda c: c.data == "confirm_finish_yes")
@check_active_test
async def confirm_finish_yes(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    await callback.answer()
    current_state = await state.get_state()
    logger.debug(f"confirm_finish_yes: current_state={current_state}")

    if current_state != TestStates.CONFIRM_FINISH.state:
        await callback.message.answer("Ваше тестирование не активно.")
        return

    user_data = await state.get_data()
    logger.debug(f"Confirm Finish Yes - user_data={user_data}")

    # Удаляем сообщение подтверждения
    confirmation_message_id = user_data.get("confirmation_message_id")
    if confirmation_message_id:
        try:
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=confirmation_message_id)
            logger.debug("Confirmation message deleted after confirm_finish_yes.")
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения подтверждения: {e}")

    test_id = user_data.get("test_id")
    test_attempt_id = user_data.get("test_attempt_id")
    answers = user_data.get("answers", {})
    questions = user_data.get("questions", [])
    user_id = callback.from_user.id
    end_time = current_time()

    # При завершении теста записываем ответы один раз в БД
    async with session.begin():
        test_result = await session.execute(select(Test).where(Test.id == test_id))
        test: Optional[Test] = test_result.scalars().first()
        if not test:
            await callback.message.answer("Тест не найден.")
            return

        user_result = await session.execute(select(User).where(User.user_id == user_id))
        user: Optional[User] = user_result.scalars().first()
        if not user:
            await callback.message.answer("Пользователь не найден в системе.")
            return

        test_attempt_result = await session.execute(
            select(TestAttempt).where(TestAttempt.id == test_attempt_id)
        )
        test_attempt: Optional[TestAttempt] = test_attempt_result.scalars().first()
        if test_attempt:
            test_attempt.answers = answers
            score, passed, detailed_answers = calculate_score(test, answers, questions)
            test_attempt.score = score
            test_attempt.passed = passed
            test_attempt.end_time = end_time
            test_attempt.answers = detailed_answers

    # Завершили запись в БД
    msg_text = (f"Вы успешно завершили тест. Спасибо за участие!\n\n"
                f"Баллы: {score}\n"
                f"Статус: {'✅ Пройден' if passed else '❌ Не пройден'}")
    msg_text = escape_markdown_v2(msg_text)
    await callback.message.answer(
        msg_text,
        parse_mode='MarkdownV2'
    )
    logger.info(
        f"User {user_id} finished test {test_id} with score={score}, passed={passed}.")

    await state.clear()
    logger.debug("State cleared after confirm_finish_yes")

    disabled_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Завершить тест (недоступно)", callback_data="noop")
        ]
    ])

    try:
        await callback.message.edit_reply_markup(reply_markup=disabled_keyboard)
        logger.debug("Finish test buttons disabled successfully after confirm_finish_yes.")
    except TelegramBadRequest as e:
        logger.error(f"Ошибка при редактировании кнопок после завершения теста: {e}")

    main_menu = get_main_menu(user.username, True)
    menu_text = "Вы можете выбрать следующий тест или воспользоваться другими опциями."
    menu_text = escape_markdown_v2(menu_text)
    await callback.message.answer(
        menu_text,
        reply_markup=main_menu,
        parse_mode='MarkdownV2'
    )
    logger.debug("Main menu sent after finishing test manually.")


@router.callback_query(lambda c: c.data == "confirm_finish_no")
@check_active_test
async def confirm_finish_no(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_data = await state.get_data()
    logger.debug(f"confirm_finish_no: user_data={user_data}")

    confirmation_message_id = user_data.get("confirmation_message_id")
    if confirmation_message_id:
        try:
            await callback.message.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=confirmation_message_id
            )
            logger.debug("Confirmation message deleted after confirm_finish_no.")
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения подтверждения: {e}")

    await state.update_data(confirmation_message_id=None)
    await state.set_state(TestStates.TESTING.state)
    logger.debug("State changed to TESTING after confirm_finish_no")

    logger.debug("Calling send_question from confirm_finish_no")
    await send_question(callback.message, state)


@router.callback_query(lambda c: c.data == "noop")
async def noop_handler(callback: types.CallbackQuery):
    await callback.answer()
    logger.debug("noop_handler called, doing nothing.")


@router.callback_query(lambda c: c.data == "cancel_editing")
@check_active_test
async def cancel_editing(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    logger.debug("cancel_editing called")

    current_state = await state.get_state()
    logger.debug(f"cancel_editing: current_state={current_state}")

    if current_state != TestStates.EDITING.state:
        await callback.message.answer("Вы не в режиме редактирования.")
        return

    await state.set_state(TestStates.TESTING)
    logger.debug("State changed to TESTING after cancel_editing")
    logger.debug("Calling send_question from cancel_editing")
    await send_question(callback.message, state)


async def send_question(message: types.Message, state: FSMContext):
    logger.debug("send_question called")
    user_data = await state.get_data()
    current_state = await state.get_state()
    editing_question_id = user_data.get("editing_question_id")
    logger.debug(f"send_question: user_data={user_data}, current_state={current_state}")

    questions = user_data.get("questions", [])
    current_index = user_data.get("current_index", 0)
    if not questions or current_index >= len(questions):
        await message.answer("Вопросы отсутствуют.")
        logger.debug("No questions to display in send_question")
        return

    current_question = questions[current_index]
    answers = user_data.get("answers", {})

    end_time = user_data.get("end_time")
    now = current_time()
    delta = end_time - now
    minutes, seconds = divmod(int(delta.total_seconds()), 60)
    time_left_str = f"{minutes} мин {seconds} сек"


    question_number = f"{current_index + 1}/{len(questions)}"
    question_lines = [
        f"Вопрос {question_number}",
        f"(Оставшееся время: {time_left_str})\n",
        current_question.question_text,
        "\n"
    ]

    editing_mode = (current_state == TestStates.EDITING.state)
    editing_this_question = editing_mode and editing_question_id == current_question.id



    buttons = []

    if current_question.question_type == "text_input":
        current_answer = answers.get(str(current_question.id), "")
        question_lines.append(f"Текущий ответ: {current_answer if current_answer else 'Нет ответа'}\n")
        if editing_this_question:
            question_lines.append("Ответ редактируется 🔨. Напишите ответ на вопрос.\n")
        question_lines.append(f"Чтобы дать ответ на текстовый вопрос, нажмите кнопку редактировать")
        if editing_this_question:
            edit_button = InlineKeyboardButton(
                text="❌ Отменить редактирование",
                callback_data="cancel_editing"
            )
        else:
            edit_button = InlineKeyboardButton(
                text="✏️ Редактировать ответ",
                callback_data=f"edit_answer:{current_question.id}"
            )
        buttons.append([edit_button])

    else:
        if current_question.question_type == "single_choice":
            question_lines.append("Выберите один вариант ответа:\n")
        elif current_question.question_type == "multiple_choice":
            question_lines.append("Выберите один или несколько вариантов ответа:\n")

        option_buttons = []
        for idx, option in enumerate(current_question.options, start=1):
            if current_question.question_type == "single_choice":
                is_selected = (str(option["id"]) == str(answers.get(str(current_question.id), "")))
            elif current_question.question_type == "multiple_choice":
                is_selected = (str(option["id"]) in str(answers.get(str(current_question.id), "")))
            else:
                is_selected = False

            checkmark = "✅" if is_selected else ""
            line = f"{idx}. {option['text']} {checkmark}"
            question_lines.append(line)

            button_text = f"{idx} {checkmark}"
            option_buttons.append(
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"answer:{option['id']}"
                )
            )
        buttons.append(option_buttons)

    prev_callback = "noop" if editing_this_question else "navigate:prev"
    next_callback = "noop" if editing_this_question else "navigate:next"

    navigation_buttons = []
    if current_index > 0:
        navigation_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад", callback_data=prev_callback))
    navigation_buttons.append(InlineKeyboardButton(
        text=f"{current_index + 1}/{len(questions)}", callback_data="noop"))
    if current_index < len(questions) - 1:
        navigation_buttons.append(InlineKeyboardButton(
            text="➡️ Вперед", callback_data=next_callback))

    navigation_buttons.append(InlineKeyboardButton(
        text="✅ Завершить тест", callback_data="finish_test"))

    if navigation_buttons:
        buttons.append(navigation_buttons)
    if current_index == len(questions) - 1:
        question_lines.append("\nЧтобы завершить тест, нажмите на кнопку \"✅ Завершить тест\".")

    question_text = "\n".join(question_lines)
    logger.debug(f"Raw question_text: {question_text}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    message_id = user_data.get("message_id")
    logger.debug(f"send_question: message_id={message_id}, editing_mode={editing_mode}, editing_this_question={editing_this_question}")
    try:
        if message_id:
            await message.bot.edit_message_text(
                text=question_text,
                chat_id=message.chat.id,
                message_id=message_id,
                reply_markup=keyboard
            )
            logger.debug("Message edited successfully in send_question")
        else:
            msg = await message.answer(question_text, reply_markup=keyboard)
            await state.update_data(message_id=msg.message_id)
            logger.debug("New message sent in send_question, message_id updated")
    except TelegramBadRequest as e:
        logger.error(f"Ошибка при редактировании/отправке сообщения: {e}")
        try:
            msg = await message.answer(question_text, reply_markup=keyboard)
            await state.update_data(message_id=msg.message_id)
            logger.debug("Sent new message without parse_mode after edit failure in send_question")
        except Exception as err:
            logger.error(f"Даже без parse_mode ошибка: {err}")

logger.debug("test_passing.py module loaded")
