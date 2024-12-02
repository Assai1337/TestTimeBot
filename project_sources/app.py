from flask import Flask, render_template, request, redirect, url_for, flash, session as flask_session
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tools.models import Base, User, Test, Question, TestAttempt, Group
import tools.config as config
import datetime

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
        flask_session['questions_data'] = []

        # Переходим на страницу создания вопросов
        return redirect(url_for('create_questions', test_id='temp', num_questions=question_count))

    # Обработка GET-запроса для отображения формы
    with DbSession() as db_session:
        groups = db_session.query(Group).all()
    return render_template('create_test.html', groups=groups)


# Создание вопросов для теста
@app.route('/create_questions/<string:test_id>/<int:num_questions>', methods=['GET', 'POST'])
def create_questions(test_id, num_questions):
    if request.method == 'POST':
        # Получаем данные вопроса из формы
        question_text = request.form.get('question_text').strip()
        question_type = request.form.get('question_type')

        if not question_text:
            flash('Текст вопроса обязателен для заполнения.')
            return redirect(url_for('create_questions', test_id=test_id, num_questions=num_questions))

        question_data = {
            'question_text': question_text,
            'question_type': question_type,
            'options': [],
            'right_answer': ''
        }

        # Список для хранения сообщений об ошибках
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

        # Если есть ошибки, отображаем их и возвращаемся к форме
        if errors:
            for error in errors:
                flash(error)
            return redirect(url_for('create_questions', test_id=test_id, num_questions=num_questions))

        # Сохраняем данные вопроса в сессии Flask
        flask_session['questions_data'].append(question_data)
        flask_session.modified = True  # Обновление сессии для сохранения изменений

        # Проверяем, нужно ли создавать ещё вопросы
        if num_questions > 1:
            return redirect(url_for('create_questions', test_id=test_id, num_questions=num_questions - 1))
        else:
            return redirect(url_for('save_test'))

    # GET-запрос для отображения формы создания вопроса
    return render_template('create_questions.html', test_id=test_id, num_questions=num_questions)

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
            groups = request.form.getlist('groups')
            test.groups_with_access = ", ".join(groups) if groups else None

            # Сохраняем изменения
            db_session.commit()
            flash('Тест успешно обновлён.')
            return redirect(url_for('admin_panel'))

        # Получаем список групп для отображения в форме
        groups = db_session.query(Group).all()
        selected_groups = test.groups_with_access.split(", ") if test.groups_with_access else []

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


@app.route('/edit_question/<int:question_id>', methods=['GET', 'POST'])
def edit_question(question_id):
    with DbSession() as db_session:
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

    return render_template('edit_question.html', question=question)

@app.route('/view_results/<int:test_id>', methods=['GET'], endpoint='view_results')
def view_results(test_id):
    with DbSession() as db_session:
        test = db_session.query(Test).filter_by(id=test_id).first()
        if not test:
            flash('Тест не найден.')
            return redirect(url_for('admin_panel'))

        # Получаем параметры фильтра из URL
        user_id = request.args.get('user_id')
        passed = request.args.get('passed')

        # Базовый запрос
        query = db_session.query(TestAttempt).filter_by(test_id=test_id)

        # Применяем фильтры
        if user_id:
            query = query.filter(TestAttempt.user_id == user_id)
        if passed == 'true':
            query = query.filter(TestAttempt.passed == True)
        elif passed == 'false':
            query = query.filter(TestAttempt.passed == False)

        attempts = query.all()

    return render_template('view_results.html', test=test, attempts=attempts)


# Сохранение теста и всех вопросов в базу данных после завершения
@app.route('/save_test')
def save_test():
    print(f"Session test_data: {flask_session.get('test_data')}")
    print(f"Session questions_data: {flask_session.get('questions_data')}")
    # Проверяем, что данные теста и вопросов есть в сессии Flask
    if 'test_data' not in flask_session or 'questions_data' not in flask_session:
        flash('Не удалось сохранить тест. Повторите попытку.')
        return redirect(url_for('create_test'))
    print(f"Current session questions_data: {flask_session['questions_data']}")

    test_data = flask_session['test_data']
    questions_data = flask_session['questions_data']

    # Сохраняем тест и вопросы в базе данных в одной транзакции
    with DbSession() as db_session:
        test = Test(
            test_name=test_data['test_name'],
            description=test_data['description'],
            question_count=test_data['question_count'],
            expiry_date=datetime.datetime.strptime(test_data['expiry_date'], "%Y-%m-%dT%H:%M") if test_data[
                'expiry_date'] else None,
            scores_need_to_pass=test_data['scores_need_to_pass'],
            groups_with_access=", ".join(test_data['groups']) if test_data['groups'] else None,
            duration=test_data['duration'],
            number_of_attempts=test_data['number_of_attempts']
        )
        db_session.add(test)
        db_session.flush()  # Получаем ID теста для добавления вопросов
        print(questions_data)
        # Добавляем каждый вопрос
        for q_data in questions_data:
            print(f"Adding question: {q_data}")  # Отладочный вывод
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
            print("Questions committed successfully.")
        except Exception as e:
            print(f"Error while committing questions: {e}")
            db_session.rollback()
            flash('Ошибка при сохранении вопросов.')
            return redirect(url_for('create_test'))

    # Очищаем сессию Flask
    flask_session.pop('test_data', None)
    flask_session.pop('questions_data', None)

    return redirect(url_for('admin_panel'))


if __name__ == '__main__':
    app.run(debug=True)
