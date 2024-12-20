// Функция для автоматической отправки формы при изменении фильтра
function autoSubmitForm() {
    document.getElementById('filter-form').submit();
}

// Функция для отображения пользователей, сдавших тест
function showSuccessfulUsers() {
    const form = document.getElementById('filter-form');
    const successfulInput = document.createElement('input');
    successfulInput.type = 'hidden';
    successfulInput.name = 'successful_users';
    successfulInput.value = 'true';
    form.appendChild(successfulInput);
    form.submit();
}

// Функция для скачивания результатов
function downloadResults(testId) {
    window.location.href = `/download_results/${testId}`;
}
