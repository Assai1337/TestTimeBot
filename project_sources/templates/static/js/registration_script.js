// static/js/registration_script.js

document.addEventListener('DOMContentLoaded', () => {
    const selectAllBtn = document.getElementById('select-all');
    const confirmBtn = document.getElementById('confirm-selected');
    const deleteBtn = document.getElementById('delete-selected');
    const userCheckboxes = document.querySelectorAll('.user-checkbox');

    // Функция для переключения выбора всех чекбоксов
    selectAllBtn.addEventListener('click', () => {
        const allChecked = Array.from(userCheckboxes).every(cb => cb.checked);
        userCheckboxes.forEach(cb => cb.checked = !allChecked);
        selectAllBtn.textContent = allChecked ? 'Выбрать всех' : 'Снять выбор';
    });

    // Функция для получения выбранных ID пользователей
    const getSelectedUserIds = () => {
        const selected = [];
        userCheckboxes.forEach(cb => {
            if (cb.checked) {
                selected.push(cb.getAttribute('data-user-id'));
            }
        });
        return selected;
    };

    // Функция для отправки запросов на сервер
    const sendRequest = async (url, data) => {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        return response.json();
    };

    // Обработчик подтверждения выбранных пользователей
    confirmBtn.addEventListener('click', async () => {
        const userIds = getSelectedUserIds();
        if (userIds.length === 0) {
            alert('Выберите пользователей для подтверждения.');
            return;
        }
        if (!confirm('Вы уверены, что хотите подтвердить выбранных пользователей?')) {
            return;
        }

        const result = await sendRequest('/api/confirm_users', { user_ids: userIds });
        if (result.success) {
            alert(result.message);
            // Удаляем строки подтвержденных пользователей из таблицы
            userIds.forEach(id => {
                const checkbox = document.querySelector(`.user-checkbox[data-user-id="${id}"]`);
                if (checkbox) {
                    const row = checkbox.closest('tr');
                    if (row) row.remove();
                }
            });
        } else {
            alert('Ошибка: ' + result.message);
        }
    });

    // Обработчик удаления выбранных пользователей
    deleteBtn.addEventListener('click', async () => {
        const userIds = getSelectedUserIds();
        if (userIds.length === 0) {
            alert('Выберите пользователей для удаления.');
            return;
        }
        if (!confirm('Вы уверены, что хотите удалить выбранных пользователей?')) {
            return;
        }

        const result = await sendRequest('/api/delete_users', { user_ids: userIds });
        if (result.success) {
            alert(result.message);
            // Удаляем строки удалённых пользователей из таблицы
            userIds.forEach(id => {
                const checkbox = document.querySelector(`.user-checkbox[data-user-id="${id}"]`);
                if (checkbox) {
                    const row = checkbox.closest('tr');
                    if (row) row.remove();
                }
            });
        } else {
            alert('Ошибка: ' + result.message);
        }
    });
});
