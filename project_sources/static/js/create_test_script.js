// Функция для валидации формы перед отправкой
function validateForm(event) {
    const description = document.querySelector('textarea[name="description"]').value.trim();
    const groupCheckboxes = document.querySelectorAll('input[name="groups"]:checked');
    const questionCount = document.querySelector('input[name="question_count"]').value;
    const scoresToPass = document.querySelector('input[name="scores_need_to_pass"]').value;
    const expiryDate = document.querySelector('input[name="expiry_date"]').value;
    const number_of_attempts = document.querySelector('input[name="number_of_attempts"]').value;

    // Проверка описания
    if (!description) {
        alert('Описание теста обязательно для заполнения.');
        event.preventDefault();
        return false;
    }

    // Проверка групп
    if (groupCheckboxes.length === 0) {
        alert('Выберите хотя бы одну группу, которой будет доступен тест.');
        event.preventDefault();
        return false;
    }

    // Проверка баллов для прохождения
    if (parseInt(scoresToPass) > parseInt(questionCount)) {
        alert('Баллы для прохождения не могут превышать количество вопросов.');
        event.preventDefault();
        return false;
    }

    // Проверка даты окончания
    if (expiryDate) {
        const now = new Date();
        const expiry = new Date(expiryDate);
        const diffMinutes = (expiry - now) / 60000; // Разница в минутах

        if (diffMinutes < 1) {
            alert('Дата окончания теста должна быть минимум через 1 минут от текущего времени.');
            event.preventDefault();
            return false;
        }
    } else {
        alert('Укажите дату окончания теста.');
        event.preventDefault();
        return false;
    }
    return true;
}
