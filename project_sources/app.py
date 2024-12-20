from flask import Flask, render_template, request, redirect, url_for, flash, session as flask_session
from flask import make_response
import pandas as pd
from flask import abort
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker,joinedload
from tools.models import Base, User, Test, Question, TestAttempt, Group
import tools.config as config
import datetime
from io import BytesIO
from urllib.parse import quote
import pandas as pd

app = Flask(__name__,
            static_folder='templates/static',
            template_folder='templates')

app.secret_key = 'supersecretkey'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
Session(app)

# Настройка базы данных PostgreSQL
engine = create_engine(config.DATABASE_URL.replace("+asyncpg", ''))
Base.metadata.create_all(engine)
DbSession = sessionmaker(bind=engine)


# Панель администратора для просмотра всех тестов
@app.route('/admin')
def admin_panel():
    with DbSession() as db_session:
        tests = db_session.query(Test).all()
    return render_template('admin_panel.html', tests=tests)


# Создание теста - страница с формой
@app.route('/create_test', methods=['GET', 'POST'])
def create_test():
    if request.method == 'POST':
        # Получаем данные из формы
        test_name = request.form['test_name']
        description = request.form.get('description')
        question_count = int(request.form['question_count'])
        expiry_date = request.form.get('expiry_date')
        scores_need_to_pass = int(request.form['scores_need_to_pass'])
        groups = request.form.getlist('groups')
        duration = int(request.form['duration'])
        number_of_attempts = int(request.form['number_of_attempts'])
        # Проверка на максимальные баллы
        if scores_need_to_pass > question_count:
            flash('Количество баллов для прохождения не может превышать количество вопросов.')
            return redirect(url_for('create_test'))
        if duration < 1:
            flash('Время на прохождение должно быть больше либо равно 1 минуте.')
            return redirect(url_for('create_test'))
        if not test_name or question_count < 1:
            flash('Название теста и количество вопросов обязательны для заполнения')
            return redirect(url_for('create_test'))

        # Сохраняем данные теста в сессии Flask
        flask_session['test_data'] = {
            'test_name': test_name,
            'description': description,
            'question_count': question_count,
            'expiry_date': expiry_date,
            'scores_need_to_pass': scores_need_to_pass,
            'groups': groups,
            'duration': duration,
            'number_of_attempts': number_of_attempts
        }
        flask_session['questions_data'] = [None] * question_count  # Инициализируем список вопросов заданной длины

        # Переходим на страницу создания вопросов
        return redirect(url_for('create_questions', test_id='temp', num_questions=question_count, question_index=0))

    # Обработка GET-запроса для отображения формы
    with DbSession() as db_session:
        groups = db_session.query(Group).all()
    return render_template('create_test.html', groups=groups)


# Создание вопросов для теста
@app.route('/create_questions/<string:test_id>/<int:num_questions>/<int:question_index>', methods=['GET', 'POST'])
def create_questions(test_id, num_questions, question_index):
    if 'test_data' not in flask_session or 'questions_data' not in flask_session:
        flash('Сессия истекла. Пожалуйста, начните создание теста заново.')
        return redirect(url_for('create_test'))

    if request.method == 'POST':
        # Получаем действие из скрытого поля
        action = request.form.get('action')

        if action == 'prev':
            # Переходим к предыдущему вопросу без сохранения данных
            if question_index > 0:
                return redirect(url_for('create_questions', test_id=test_id, num_questions=num_questions, question_index=question_index - 1))
            else:
                return redirect(url_for('create_questions', test_id=test_id, num_questions=num_questions, question_index=0))

        elif action in ['next', 'save']:
            # Сохраняем данные вопроса
            question_text = request.form.get('question_text', '').strip()
            question_type = request.form.get('question_type', '').strip()

            question_data = {
                'question_text': question_text,
                'question_type': question_type,
                'options': [],
                'right_answer': ''
            }

            errors = []

            # Для вопросов с вариантами ответа
            if question_type in ['single_choice', 'multiple_choice']:
                options = request.form.getlist('options')  # Список вариантов
                correct_options = request.form.getlist('correct_options')  # Правильные варианты

                # Проверка наличия минимум двух вариантов ответа
                if len(options) < 2:
                    errors.append('Должно быть минимум два варианта ответа.')

                # Проверка, что варианты ответов не пустые
                for idx, option_text in enumerate(options, start=1):
                    option_text = option_text.strip()
                    if not option_text:
                        errors.append(f'Вариант ответа #{idx} не может быть пустым.')
                    else:
                        # Формируем структуру варианта ответа с уникальным id
                        option = {
                            "id": idx,  # Уникальный номер варианта
                            "text": option_text,  # Текст варианта
                            "is_correct": str(idx) in correct_options  # Правильный ли вариант
                        }
                        question_data['options'].append(option)
                        # Формируем правильный ответ для хранения
                        if str(idx) in correct_options:
                            question_data['right_answer'] += str(idx)

                # Проверка наличия хотя бы одного правильного варианта
                if not correct_options:
                    errors.append('Необходимо выбрать хотя бы один правильный вариант ответа.')

            # Для текстовых вопросов
            elif question_type == 'text_input':
                text_answer = request.form.get('text_answer', '').strip()
                if not text_answer:
                    errors.append('Ответ не может быть пустым для текстового вопроса.')
                else:
                    question_data['right_answer'] = text_answer.lower()

            else:
                errors.append('Некорректный тип вопроса.')

            # Если есть ошибки, отображаем их и остаёмся на текущем вопросе
            if errors:
                for error in errors:
                    flash(error)
                return redirect(url_for('create_questions', test_id=test_id, num_questions=num_questions, question_index=question_index))

            # Сохраняем данные вопроса в сессии по индексу вопроса
            flask_session['questions_data'][question_index] = question_data
            flask_session.modified = True  # Обновление сессии для сохранения изменений

            if action == 'save':
                # Выполняем сохранение теста и вопросов
                test_data = flask_session['test_data']
                questions_data = flask_session['questions_data']

                # Проверяем, что все вопросы заполнены
                if any(q is None for q in questions_data):
                    missing_index = flask_session['questions_data'].index(None)
                    flash('Не все вопросы заполнены.')
                    return redirect(url_for('create_questions', test_id=test_id, num_questions=num_questions, question_index=missing_index))

                # Сохраняем тест и вопросы в базе данных в одной транзакции
                with DbSession() as db_session:
                    test = Test(
                        test_name=test_data['test_name'],
                        description=test_data['description'],
                        question_count=test_data['question_count'],
                        expiry_date=datetime.datetime.strptime(test_data['expiry_date'], "%Y-%m-%dT%H:%M") if test_data['expiry_date'] else None,
                        scores_need_to_pass=test_data['scores_need_to_pass'],
                        groups_with_access=", ".join(test_data['groups']) if test_data['groups'] else None,
                        duration=test_data['duration'],
                        number_of_attempts=test_data['number_of_attempts']
                    )
                    db_session.add(test)
                    db_session.flush()  # Получаем ID теста для добавления вопросов

                    # Добавляем каждый вопрос
                    for q_data in questions_data:
                        question = Question(
                            test_id=test.id,
                            question_text=q_data['question_text'],
                            question_type=q_data['question_type'],
                            options=q_data['options'] if 'options' in q_data else None,
                            right_answer=q_data['right_answer']
                        )
                        db_session.add(question)

                    try:
                        db_session.commit()
                    except Exception as e:
                        db_session.rollback()
                        flash('Ошибка при сохранении вопросов.')
                        return redirect(url_for('create_test'))

                # Очищаем сессию Flask
                flask_session.pop('test_data', None)
                flask_session.pop('questions_data', None)

                flash('Тест успешно создан.')
                return redirect(url_for('admin_panel'))

            elif action == 'next':
                # Переходим к следующему вопросу
                if question_index + 1 < num_questions:
                    return redirect(url_for('create_questions', test_id=test_id, num_questions=num_questions, question_index=question_index + 1))
                else:
                    # Если это последний вопрос, предлагаем сохранить тест
                    flash('Вы заполнили все вопросы. Проверьте их и сохраните тест.')
                    return redirect(url_for('create_questions', test_id=test_id, num_questions=num_questions, question_index=question_index))

    # GET-запрос для отображения формы создания вопроса
    # Получаем данные вопроса из сессии, если они есть
    question_data = None
    if 'questions_data' in flask_session and 0 <= question_index < num_questions:
        question_data = flask_session['questions_data'][question_index]

    return render_template('create_questions.html', test_id=test_id, num_questions=num_questions, question_index=question_index, question_data=question_data)


# Редактирование теста
@app.route('/edit_test/<int:test_id>', methods=['GET', 'POST'])
def edit_test(test_id):
    with DbSession() as db_session:
        test = db_session.query(Test).filter_by(id=test_id).first()
        if not test:
            flash('Тест не найден.')
            return redirect(url_for('admin_panel'))

        if request.method == 'POST':
            # Обновляем данные теста
            test.test_name = request.form['test_name']
            test.description = request.form.get('description')
            test.question_count = int(request.form['question_count'])
            expiry_date = request.form.get('expiry_date')
            test.expiry_date = datetime.datetime.strptime(expiry_date, "%Y-%m-%dT%H:%M") if expiry_date else None
            test.scores_need_to_pass = int(request.form['scores_need_to_pass'])
            test.duration = int(request.form['duration'])
            test.number_of_attempts = int(request.form['number_of_attempts'])
            groups = request.form.getlist('groups')  # Список названий групп
            test.groups_with_access = ", ".join(groups) if groups else None

            # Валидация данных
            errors = []
            if test.scores_need_to_pass > test.question_count:
                errors.append("Баллы для прохождения не могут превышать количество вопросов.")
            if test.duration < 1:
                errors.append("Длительность теста должна быть не менее 1 минуты.")
            if test.expiry_date and (test.expiry_date - datetime.datetime.utcnow()) < datetime.timedelta(minutes=1):
                errors.append("Дата окончания должна быть больше текущего времени на 1 минуту.")

            if errors:
                for error in errors:
                    flash(error, 'error')
                # Остаёмся на странице редактирования теста
                return redirect(url_for('edit_test', test_id=test.id))
            else:
                db_session.commit()
                flash('Тест успешно обновлён.', 'success')
                return redirect(url_for('admin_panel'))

        # Получаем список групп для отображения в форме
        groups = db_session.query(Group).all()
        # Парсим список названий групп с доступом
        selected_groups = [g.strip() for g in test.groups_with_access.split(",")] if test.groups_with_access else []

    return render_template('edit_test.html', test=test, groups=groups, selected_groups=selected_groups)


# Отображение списка вопросов для редактирования
@app.route('/edit_questions/<int:test_id>', methods=['GET'])
def edit_questions(test_id):
    with DbSession() as db_session:
        test = db_session.query(Test).filter_by(id=test_id).first()
        if not test:
            flash('Тест не найден.')
            return redirect(url_for('admin_panel'))

        questions = db_session.query(Question).filter_by(test_id=test_id).all()

    return render_template('edit_questions.html', test=test, questions=questions)


# Редактирование вопроса
@app.route('/edit_question/<int:question_id>', methods=['GET', 'POST'])
def edit_question(question_id):
    with DbSession() as db_session:
        # Получаем вопрос из базы данных
        question = db_session.query(Question).filter_by(id=question_id).first()
        if not question:
            flash('Вопрос не найден.')
            return redirect(url_for('admin_panel'))

        if request.method == 'POST':
            # Получаем данные из формы
            question_text = request.form.get('question_text')
            question_type = request.form.get('question_type')

            if not question_text:
                flash('Текст вопроса обязателен для заполнения.')
                return redirect(url_for('edit_question', question_id=question_id))

            question.question_text = question_text
            question.question_type = question_type

            # Обработка вариантов ответов
            if question_type in ['single_choice', 'multiple_choice']:
                options_texts = request.form.getlist('options')
                correct_options = request.form.getlist('correct_options')

                options = []
                for idx, option_text in enumerate(options_texts, start=1):
                    option = {
                        'id': idx,
                        'text': option_text.strip(),
                        'is_correct': str(idx) in correct_options
                    }
                    options.append(option)

                question.options = options
                # Формируем правильный ответ для хранения
                right_answer = ''.join([str(opt['id']) for opt in options if opt['is_correct']])
                question.right_answer = right_answer
            elif question_type == 'text_input':
                text_answer = request.form.get('text_answer')
                question.right_answer = text_answer.lower()
                question.options = None
            else:
                flash('Неизвестный тип вопроса.')
                return redirect(url_for('edit_question', question_id=question_id))

            # Сохраняем изменения
            db_session.commit()
            flash('Вопрос успешно обновлён.')
            return redirect(url_for('edit_questions', test_id=question.test_id))

    return render_template('edit_question.html', question=question, question_id=question_id)



# Отображение результатов теста
@app.route('/view_results/<int:test_id>')
def view_results(test_id):
    with DbSession() as db_session:
        # Получение теста
        test = db_session.query(Test).filter_by(id=test_id).first()
        if not test:
            flash('Тест не найден.')
            return redirect(url_for('admin_panel'))

        # Получение фильтров из GET-параметров
        selected_groups = [g.strip() for g in request.args.getlist('group') if g.strip()]
        selected_status = request.args.get('status')
        successful_users = request.args.get('successful_users')

        # Начало запроса для получения попыток с жадной загрузкой связанных данных
        query = db_session.query(TestAttempt).options(
            joinedload(TestAttempt.user).joinedload(User.group_rel)
        ).filter(TestAttempt.test_id == test_id)

        # Применение фильтра по группам, если выбран
        if selected_groups:
            query = query.join(TestAttempt.user).filter(User.group_rel.has(Group.groupname.in_(selected_groups)))

        # Применение фильтра по статусу прохождения, если выбран
        if selected_status == 'passed':
            query = query.filter(TestAttempt.passed == True)
        elif selected_status == 'failed':
            query = query.filter(TestAttempt.passed == False)

        # Если выбраны успешные пользователи, фильтруем по лучшим попыткам
        if successful_users == 'true':
            all_attempts = query.filter(TestAttempt.passed == True).all()
            best_attempts = {}
            for attempt in all_attempts:
                user_id = attempt.user.id
                if user_id not in best_attempts or best_attempts[user_id].score < attempt.score:
                    best_attempts[user_id] = attempt
            attempts = list(best_attempts.values())
        else:
            attempts = query.all()

        # Получение всех групп для отображения в фильтре
        groups = db_session.query(Group).all()

    return render_template(
        'view_results.html',
        test=test,
        attempts=attempts,
        groups=groups,
        selected_groups=selected_groups,
        selected_status=selected_status
    )

from flask import make_response
from io import BytesIO
import pandas as pd

@app.route('/download_results/<int:test_id>', methods=['GET'])
def download_results(test_id):
    with DbSession() as db_session:
        # Получение теста
        test = db_session.query(Test).filter_by(id=test_id).first()
        if not test:
            flash('Тест не найден.')
            return redirect(url_for('view_results', test_id=test_id))

        # Получение всех попыток
        attempts = db_session.query(TestAttempt).options(
            joinedload(TestAttempt.user).joinedload(User.group_rel)
        ).filter(TestAttempt.test_id == test_id).all()

        # Формирование данных для Excel
        user_best_attempts = {}
        for attempt in attempts:
            user_id = attempt.user.id
            # Сохраняем только самую успешную попытку
            if user_id not in user_best_attempts or user_best_attempts[user_id].score < attempt.score:
                user_best_attempts[user_id] = attempt

        # Подготовка данных для DataFrame
        data = []
        for attempt in user_best_attempts.values():
            data.append({
                "ФИО": f"{attempt.user.firstname} {attempt.user.lastname} {attempt.user.middlename or ''}".strip(),
                "Группа": attempt.user.group_rel.groupname,
                "Балл за попытку": f"{attempt.score} / {test.question_count}" if test.question_count else f"{attempt.score} / -",
                "Статус": "Сдал" if attempt.passed else "Не сдал"
            })

        # Создание DataFrame
        df = pd.DataFrame(data)

        # Создание Excel файла в буфере
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name="Results")
        output.seek(0)

        # Формирование имени файла
        original_filename = f"{test.test_name.replace(' ', '_')}.xlsx"
        ascii_filename = quote(original_filename)  # Кодирование имени файла в ASCII

        # Создание HTTP-ответа с вложением
        response = make_response(output.read())
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{ascii_filename}"
        response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return response


if __name__ == '__main__':
    app.run(debug=True)
