from tools.models import Test, Question  #
from typing import Dict, Any, List, Tuple

def calculate_score(test: Test, user_answers: Dict[str, Any], questions: List[Question]) -> Tuple[int, bool, Dict[str, Any]]:
    """
    Вычисляет балл, определяет, прошёл ли пользователь тест, и возвращает подробные ответы с информацией о правильности.

    :param test: Экземпляр теста.
    :param user_answers: Словарь ответов пользователя {question_id: user_answer}.
    :param questions: Список вопросов.
    :return: Кортеж (score, passed, detailed_answers).
    """
    total_score = 0
    total_possible_score = 0
    detailed_answers = {}

    for question in questions:
        question_id_str = str(question.id)
        user_answer = user_answers.get(question_id_str)
        is_correct = False
        question_score = 1  # По умолчанию балл за вопрос равен 1

        if user_answer is not None:
            if question.question_type == 'single_choice':
                correct_option_ids = list(question.right_answer)
                is_correct = str(user_answer) == question.right_answer

            elif question.question_type == 'multiple_choice':
                correct_option_ids = list(question.right_answer)
                user_answer_ids = list(str(user_answer))
                is_correct = set(user_answer_ids) == set(correct_option_ids)

            elif question.question_type == 'text_input':
                correct_answer = question.right_answer.strip().lower() if question.right_answer else ""
                user_input = user_answer.strip().lower()
                is_correct = user_input == correct_answer

            else:
                pass

            # Обновляем общий балл
            if is_correct:
                total_score += question_score
            total_possible_score += question_score

            # Сохраняем подробный ответ
            detailed_answers[question_id_str] = {
                'user_answer': user_answer,
                'correct': is_correct
            }
        else:
            # Если ответа нет, сохраняем это
            detailed_answers[question_id_str] = {
                'user_answer': None,
                'correct': False
            }
            total_possible_score += question_score

    # Определяем, прошёл ли пользователь тест
    passing_score = test.scores_need_to_pass if hasattr(test, 'scores_need_to_pass') else 0
    passed = total_score >= passing_score

    return total_score, passed, detailed_answers
