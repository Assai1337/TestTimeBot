// static/js/create_questions_script.js

// Функция для добавления нового варианта ответа
function addOption(optionText = '', isCorrect = false) {
    const container = document.getElementById('options_container');
    const optionCount = container.querySelectorAll('.option').length + 1;
    const newOption = document.createElement('div');
    newOption.classList.add('option');
    newOption.innerHTML = `
        <input type="text" name="options" value="${optionText}" required>
        <label>Правильный:
            <input type="checkbox" name="correct_options" class="correct-checkbox" value="${optionCount}" ${isCorrect ? 'checked' : ''}>
        </label>
        <button type="button" class="delete-option-button" onclick="deleteOption(this)">&#10006;</button>
    `;
    container.appendChild(newOption);
    updateOptionIndices();
    updateOptionBehavior(); // Обновляем поведение чекбоксов
}

// Функция для удаления варианта ответа
function deleteOption(button) {
    const option = button.parentElement;
    const container = document.getElementById('options_container');
    const options = container.querySelectorAll('.option');

    // Проверяем, что количество вариантов больше 2
    if (options.length > 2) {
        option.remove();
        // Перенумеруем оставшиеся варианты и обновим значения чекбоксов
        updateOptionIndices();
    } else {
        alert('Количество вариантов ответа не может быть меньше 2.');
    }
}

// Функция для перенумерации вариантов после удаления или добавления
function updateOptionIndices() {
    const options = document.querySelectorAll('.option');
    options.forEach((option, index) => {
        const checkbox = option.querySelector('.correct-checkbox');
        checkbox.value = index + 1;
    });
}

// Функция для изменения поведения в зависимости от типа вопроса
function updateOptionBehavior() {
    const questionType = document.getElementById('question_type').value;
    const optionsContainer = document.getElementById('options_container');
    const textAnswerContainer = document.getElementById('text_answer_container');
    const addOptionButton = document.getElementById('add_option_button');

    if (questionType === "text_input") {
        optionsContainer.style.display = 'none';
        textAnswerContainer.style.display = 'block';
        addOptionButton.style.display = 'none'; // Скрываем кнопку
        // Очищаем варианты ответов
        optionsContainer.innerHTML = '';
    } else {
        optionsContainer.style.display = 'block';
        textAnswerContainer.style.display = 'none';
        addOptionButton.style.display = 'inline-block'; // Показываем кнопку

        // Если вариантов меньше 2, добавляем недостающие
        let optionCount = optionsContainer.querySelectorAll('.option').length;
        while (optionCount < 2) {
            addOption();
            optionCount++;
        }

        // Сбрасываем все обработчики событий
        const checkboxes = document.querySelectorAll('.correct-checkbox');
        checkboxes.forEach((checkbox) => {
            checkbox.onclick = null; // Сбрасываем обработчики
        });

        if (questionType === "single_choice") {
            // Для одиночного выбора разрешаем выбрать только один вариант
            checkboxes.forEach((checkbox) => {
                checkbox.addEventListener('click', singleChoiceHandler);
            });
        } else if (questionType === "multiple_choice") {
            // Для множественного выбора убираем ограничения
            checkboxes.forEach((checkbox) => {
                checkbox.removeEventListener('click', singleChoiceHandler);
            });
        }
    }
}

// Обработчик для одиночного выбора
function singleChoiceHandler() {
    const checkboxes = document.querySelectorAll('.correct-checkbox');
    checkboxes.forEach((cb) => {
        if (cb !== this) cb.checked = false;
    });
}

// Функция для валидации формы перед отправкой
function validateForm(event) {
    // Получаем значение скрытого поля 'action'
    const action = document.getElementById('action').value;
    console.log("Action:", action); // Отладочный вывод

    if (action === 'prev') {
        // Не выполняем валидацию при нажатии на "Предыдущий вопрос"
        return true;
    }

    // Продолжаем с валидацией для кнопок "next" и "save"
    const questionType = document.getElementById('question_type').value;

    const questionText = document.querySelector('textarea[name="question_text"]').value.trim();
    if (questionText === '') {
        alert('Поле текста вопроса не может быть пустым.');
        return false;
    }

    if (questionType === "text_input") {
        const textAnswer = document.querySelector('input[name="text_answer"]').value.trim();
        if (textAnswer === '') {
            alert('Поле ответа не может быть пустым.');
            return false;
        }
    } else {
        const optionInputs = document.querySelectorAll('input[name="options"]');
        const correctCheckboxes = document.querySelectorAll('.correct-checkbox:checked');
        let valid = true;

        optionInputs.forEach((input) => {
            if (input.value.trim() === '') {
                valid = false;
            }
        });

        if (!valid) {
            alert('Поля вариантов ответа не могут быть пустыми.');
            return false;
        }

        if (correctCheckboxes.length === 0) {
            alert('Необходимо выбрать хотя бы один правильный вариант ответа.');
            return false;
        }

        if (questionType === "single_choice" && correctCheckboxes.length > 1) {
            alert('Для вопроса с одиночным выбором можно выбрать только один правильный вариант.');
            return false;
        }
    }
    return true; // Если все проверки пройдены
}

// Инициализация на загрузку страницы
document.addEventListener("DOMContentLoaded", function() {
    updateOptionBehavior();

    // Добавляем обработчик события submit для формы
    const form = document.getElementById('question_form');
    form.addEventListener('submit', function(event) {
        if (!validateForm(event)) {
            event.preventDefault(); // Предотвращаем отправку формы, если валидация не пройдена
        }
    });
});
