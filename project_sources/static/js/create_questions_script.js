// static/js/create_questions_script.js

// Функция для добавления нового варианта ответа
function addOption() {
    const container = document.getElementById('options_container');
    const currentOptionCount = container.querySelectorAll('.option').length + 1;
    const newOption = document.createElement('div');
    newOption.classList.add('option');
    newOption.innerHTML = `
        <input type="text" name="options">
        <label>Правильный:
            <input type="checkbox" name="correct_options" class="correct-checkbox" value="${currentOptionCount}">
        </label>
    `;
    container.appendChild(newOption);
    updateOptionBehavior();
}

// Функция для изменения поведения в зависимости от типа вопроса
function updateOptionBehavior() {
    const questionType = document.getElementById('question_type').value;
    const checkboxes = document.querySelectorAll('.correct-checkbox');
    const optionsContainer = document.getElementById('options_container');
    const textAnswerContainer = document.getElementById('text_answer_container');
    const addOptionButton = document.getElementById('add_option_button');

    // Если тип вопроса текстовый, скрываем блок с вариантами и кнопку "Добавить вариант"
    if (questionType === "text_input") {
        optionsContainer.style.display = 'none';
        textAnswerContainer.style.display = 'block';
        addOptionButton.style.display = 'none'; // Скрываем кнопку
    } else {
        optionsContainer.style.display = 'block';
        textAnswerContainer.style.display = 'none';
        addOptionButton.style.display = 'inline-block'; // Показываем кнопку

        // Обработка поведения для одиночного и множественного выбора
        if (questionType === "single_choice") {
            checkboxes.forEach((checkbox) => {
                checkbox.checked = false;
                checkbox.onclick = function() {
                    if (this.checked) {
                        checkboxes.forEach((box) => {
                            if (box !== checkbox) box.checked = false;
                        });
                    }
                };
            });
        } else if (questionType === "multiple_choice") {
            checkboxes.forEach((checkbox) => {
                checkbox.onclick = null;
            });
        }
    }
}

// Инициализация на загрузку страницы
document.addEventListener("DOMContentLoaded", function() {
    updateOptionBehavior();
});
