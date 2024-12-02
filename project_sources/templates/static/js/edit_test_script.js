// static/js/edit_test_script.js

document.addEventListener('DOMContentLoaded', function() {
    // Блокируем поле "Количество вопросов"
    const questionCountInput = document.querySelector('input[name="question_count"]');
    questionCountInput.readOnly = true;

    // Добавляем обработчик для поля "Баллы для прохождения"
    const scoresNeedToPassInput = document.querySelector('input[name="scores_need_to_pass"]');

    scoresNeedToPassInput.addEventListener('input', function() {
        const questionCount = parseInt(questionCountInput.value, 10);
        const scoresNeedToPass = parseInt(this.value, 10);

        if (scoresNeedToPass > questionCount) {
            alert('Баллы для прохождения не могут быть больше количества вопросов.');
            this.value = questionCount;
        }
    });

    // Добавляем обработчик для поля "Дата окончания"
    const expiryDateInput = document.querySelector('input[name="expiry_date"]');

    // При отправке формы проверяем дату окончания
    const form = document.querySelector('.create-test-form');
    form.addEventListener('submit', function(event) {
        const currentTime = new Date();
        // Корректируем время на UTC+3
        currentTime.setHours(currentTime.getHours());

        const expiryDateValue = expiryDateInput.value;
        if (expiryDateValue) {
            const expiryDate = new Date(expiryDateValue);
            // Проверяем, что дата окончания как минимум на 30 минут больше текущего времени
            if (expiryDate - currentTime < 30 * 60 * 1000) {
                alert('Дата окончания должна быть больше текущего времени на 30 минут.');
                event.preventDefault();
            }
        }
    });
});
