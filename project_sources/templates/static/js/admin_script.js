// static/js/admin_script.js

document.addEventListener('DOMContentLoaded', function() {
    const table = document.getElementById('testsTable');
    const headers = table.querySelectorAll('th[data-column]');
    const tableBody = table.querySelector('tbody');
    let rows = Array.from(tableBody.querySelectorAll('tr'));
    let sortDirection = {};
    let initialSortDone = false;

    // Инициализируем направление сортировки для каждого столбца
    headers.forEach(header => {
        const column = header.getAttribute('data-column');
        sortDirection[column] = 'asc';
        header.style.cursor = 'pointer';
        header.addEventListener('click', () => {
            sortTableByColumn(column);
        });
    });

    // Функция для сортировки таблицы по указанному столбцу
    function sortTableByColumn(column) {
        const dataType = getDataType(column);
        const direction = sortDirection[column] === 'asc' ? 1 : -1;

        rows.sort((a, b) => {
            const aCell = a.cells[getColumnIndex(column)];
            const bCell = b.cells[getColumnIndex(column)];

            const aValue = aCell.getAttribute('data-value') || aCell.textContent.trim();
            const bValue = bCell.getAttribute('data-value') || bCell.textContent.trim();

            if (dataType === 'number') {
                return direction * (parseFloat(aValue) - parseFloat(bValue));
            } else if (dataType === 'date') {
                return direction * (new Date(aValue) - new Date(bValue));
            } else {
                return direction * aValue.localeCompare(bValue, 'ru');
            }
        });

        // Удаляем существующие строки из таблицы
        while (tableBody.firstChild) {
            tableBody.removeChild(tableBody.firstChild);
        }

        // Добавляем отсортированные строки в таблицу
        tableBody.append(...rows);

        // Инвертируем направление сортировки для следующего клика
        sortDirection[column] = sortDirection[column] === 'asc' ? 'desc' : 'asc';

        // Сбрасываем индикаторы сортировки
        headers.forEach(header => {
            const indicator = header.querySelector('.sort-indicator');
            if (indicator) {
                indicator.textContent = '';
            }
        });

        // Устанавливаем индикатор на текущем столбце
        const currentHeader = Array.from(headers).find(header => header.getAttribute('data-column') === column);
        const currentIndicator = currentHeader.querySelector('.sort-indicator');
        if (currentIndicator) {
            currentIndicator.textContent = sortDirection[column] === 'asc' ? '▲' : '▼';
        }
    }

    // Функция для определения типа данных столбца
    function getDataType(column) {
        if (['question_count', 'scores_need_to_pass', 'duration', 'number_of_attempts'].includes(column)) {
            return 'number';
        } else if (['creation_date', 'expiry_date'].includes(column)) {
            return 'date';
        } else {
            return 'string';
        }
    }

    // Функция для получения индекса столбца по его имени
    function getColumnIndex(column) {
        let index = -1;
        headers.forEach((header, i) => {
            if (header.getAttribute('data-column') === column) {
                index = i;
            }
        });
        return index;
    }

function highlightExpiredTests() {
    // Получаем текущее время
    const currentTime = new Date().getTime();

    rows.forEach(row => {
        const expiryDateCell = row.cells[getColumnIndex('expiry_date')];
        const expiryDateText = expiryDateCell.textContent.trim();

        // Проверяем, есть ли дата окончания и она не равна "Без окончания"
        if (expiryDateText && expiryDateText !== "Без окончания") {
            const expiryDate = new Date(expiryDateText);

            // Если дата истекла, добавляем класс
            if (expiryDate.getTime() < currentTime) {
                row.classList.add('expired-test');
            } else {
                row.classList.remove('expired-test');
            }
        }
    });
}



    // Сортируем таблицу по дате создания при загрузке страницы (в порядке убывания)
    if (!initialSortDone) {
        // Устанавливаем направление сортировки для 'creation_date' на 'desc' перед сортировкой
        sortDirection['creation_date'] = 'desc';
        sortTableByColumn('creation_date');
        initialSortDone = true;
    }

    // Выделяем истёкшие тесты
    highlightExpiredTests();
});
