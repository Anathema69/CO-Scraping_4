// DIAN - Funcionalidad

// Configuración de años disponibles
const YEAR_START = 2006;
const CURRENT_YEAR = new Date().getFullYear();
const MONTHS = [
    { value: '01', name: 'Enero' },
    { value: '02', name: 'Febrero' },
    { value: '03', name: 'Marzo' },
    { value: '04', name: 'Abril' },
    { value: '05', name: 'Mayo' },
    { value: '06', name: 'Junio' },
    { value: '07', name: 'Julio' },
    { value: '08', name: 'Agosto' },
    { value: '09', name: 'Septiembre' },
    { value: '10', name: 'Octubre' },
    { value: '11', name: 'Noviembre' },
    { value: '12', name: 'Diciembre' }
];

// Variables globales
let selectedYear = null;
let selectedMonth = null;

// Inicializar componentes al cargar la página
document.addEventListener('DOMContentLoaded', function() {
    initializeYearSelector();
    initializeYearsGrid();
    initializeForm();
});

// Inicializar selector de año
function initializeYearSelector() {
    const yearSelect = document.getElementById('year');

    // Agregar años desde el más reciente
    for (let year = CURRENT_YEAR; year >= YEAR_START; year--) {
        const option = document.createElement('option');
        option.value = year;
        option.textContent = year;
        if (year === CURRENT_YEAR) {
            option.textContent += ' (Actual)';
        }
        yearSelect.appendChild(option);
    }
}

// Inicializar grilla de años
function initializeYearsGrid() {
    const yearsGrid = document.querySelector('.years-grid');

    // Crear items de años
    for (let year = CURRENT_YEAR; year >= YEAR_START; year--) {
        const yearItem = document.createElement('div');
        yearItem.className = 'year-item';
        if (year === CURRENT_YEAR) {
            yearItem.classList.add('current');
        }
        yearItem.textContent = year;
        yearItem.onclick = () => selectYearFromGrid(year);
        yearsGrid.appendChild(yearItem);
    }
}

// Seleccionar año desde la grilla
function selectYearFromGrid(year) {
    // Actualizar selector
    document.getElementById('year').value = year;

    // Actualizar visualización de grilla
    document.querySelectorAll('.year-item').forEach(item => {
        item.classList.remove('selected');
        if (item.textContent.includes(year.toString())) {
            item.classList.add('selected');
        }
    });

    // Actualizar opciones de mes
    updateMonthOptions();

    // Scroll suave al formulario
    document.querySelector('.card').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Actualizar opciones de mes cuando se selecciona un año
function updateMonthOptions() {
    const yearSelect = document.getElementById('year');
    const monthSelect = document.getElementById('month');
    const selectedYear = yearSelect.value;

    // Limpiar opciones actuales
    monthSelect.innerHTML = '<option value="">-- Seleccione un mes --</option>';

    if (selectedYear) {
        // Habilitar selector de mes
        monthSelect.disabled = false;

        // Si es el año actual, limitar hasta el mes actual
        const currentDate = new Date();
        const maxMonth = selectedYear == CURRENT_YEAR ? currentDate.getMonth() + 1 : 12;

        // Agregar meses disponibles
        MONTHS.forEach(month => {
            if (parseInt(month.value) <= maxMonth) {
                const option = document.createElement('option');
                option.value = month.value;
                option.textContent = month.name;
                monthSelect.appendChild(option);
            }
        });

        // Actualizar visualización en grilla
        document.querySelectorAll('.year-item').forEach(item => {
            item.classList.remove('selected');
            if (item.textContent.includes(selectedYear)) {
                item.classList.add('selected');
            }
        });
    } else {
        // Deshabilitar selector de mes
        monthSelect.disabled = true;
        document.querySelectorAll('.year-item').forEach(item => {
            item.classList.remove('selected');
        });
    }

    // Actualizar estado del botón
    updateSearchButton();
}

// Actualizar estado del botón de búsqueda
function updateSearchButton() {
    const yearSelect = document.getElementById('year');
    const monthSelect = document.getElementById('month');
    const searchButton = document.getElementById('searchButton');
    const selectionPreview = document.getElementById('selectionPreview');
    const previewText = document.getElementById('previewText');

    if (yearSelect.value && monthSelect.value) {
        searchButton.disabled = false;

        // Mostrar vista previa
        const monthName = MONTHS.find(m => m.value === monthSelect.value).name;
        previewText.textContent = `${monthName} de ${yearSelect.value}`;
        selectionPreview.style.display = 'flex';
    } else {
        searchButton.disabled = true;
        selectionPreview.style.display = 'none';
    }
}

// Resetear formulario
function resetForm() {
    const form = document.getElementById('searchForm');
    form.reset();

    // Resetear selector de mes
    const monthSelect = document.getElementById('month');
    monthSelect.innerHTML = '<option value="">-- Primero seleccione un año --</option>';
    monthSelect.disabled = true;

    // Resetear visualización
    document.querySelectorAll('.year-item').forEach(item => {
        item.classList.remove('selected');
    });

    // Ocultar vista previa
    document.getElementById('selectionPreview').style.display = 'none';

    // Deshabilitar botón
    document.getElementById('searchButton').disabled = true;

    showNotification('Selección limpiada correctamente', 'info');
}

// Inicializar formulario
function initializeForm() {
    const form = document.getElementById('searchForm');
    const monthSelect = document.getElementById('month');

    // Manejar cambio en selector de mes
    monthSelect.addEventListener('change', updateSearchButton);

    // Manejar envío del formulario
    form.addEventListener('submit', function(e) {
        e.preventDefault();

        const year = document.getElementById('year').value;
        const month = document.getElementById('month').value;

        if (!year || !month) {
            showNotification('Por favor seleccione año y mes', 'warning');
            return;
        }

        // Preparar datos para envío
        const searchData = {
            year: year,
            month: month,
            monthName: MONTHS.find(m => m.value === month).name
        };

        // Mostrar datos de búsqueda (temporal)
        console.log('Datos de búsqueda:', searchData);
        showNotification(`Buscando conceptos de ${searchData.monthName} ${searchData.year}. Esta funcionalidad está en desarrollo.`, 'info');

        // Aquí se enviará la petición al backend cuando esté implementado
        // fetch('/api/dian/search', {
        //     method: 'POST',
        //     headers: {'Content-Type': 'application/json'},
        //     body: JSON.stringify(searchData)
        // })
    });
}