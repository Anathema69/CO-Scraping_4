// Biblioteca Digital CCB - Funcionalidad

// Variables globales
let currentTab = 'subcomunidades';

// Manejar cambio de tipo de arbitraje
function handleArbitrageTypeChange() {
    const select = document.getElementById('tipoArbitraje');
    const filtersCard = document.getElementById('filtersCard');
    const socialNotice = document.getElementById('socialNotice');

    if (select.value === 'nacional') {
        filtersCard.style.display = 'block';
        socialNotice.style.display = 'none';

        // Animación suave al mostrar
        filtersCard.style.opacity = '0';
        setTimeout(() => {
            filtersCard.style.transition = 'opacity 0.3s ease';
            filtersCard.style.opacity = '1';
        }, 100);
    } else if (select.value === 'social') {
        // Mostrar noticia de próximo desarrollo
        socialNotice.style.display = 'flex';
        filtersCard.style.display = 'none';

        // Resetear selección después de mostrar el mensaje
        setTimeout(() => {
            select.value = '';
            socialNotice.style.display = 'none';
        }, 3000);
    } else {
        filtersCard.style.display = 'none';
        socialNotice.style.display = 'none';
    }
}

// Cambiar pestaña activa
function setActiveTab(button, tabName) {
    // Remover clase activa de todos los botones
    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(btn => btn.classList.remove('active'));

    // Agregar clase activa al botón seleccionado
    button.classList.add('active');

    // Ocultar todos los paneles
    const tabPanes = document.querySelectorAll('.tab-pane');
    tabPanes.forEach(pane => pane.classList.remove('active'));

    // Mostrar el panel seleccionado
    const selectedPane = document.getElementById(`tab-${tabName}`);
    if (selectedPane) {
        selectedPane.classList.add('active');
    }

    currentTab = tabName;
}

// Resetear formulario
function resetForm() {
    const form = document.getElementById('searchForm');
    form.reset();

    // Resetear selector de tipo de arbitraje
    document.getElementById('tipoArbitraje').value = '';
    document.getElementById('filtersCard').style.display = 'none';

    // Volver a la primera pestaña
    const firstTabButton = document.querySelector('.tab-button');
    if (firstTabButton) {
        setActiveTab(firstTabButton, 'subcomunidades');
    }

    showNotification('Filtros limpiados correctamente', 'info');
}

// Manejar envío del formulario
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('searchForm');

    // Auto-seleccionar la opción nacional al cargar
    const tipoArbitraje = document.getElementById('tipoArbitraje');
    if (tipoArbitraje && tipoArbitraje.value === 'nacional') {
        handleArbitrageTypeChange();
    }

    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();

            // Recopilar datos según la pestaña activa
            let searchData = {
                tipo: 'arbitraje_nacional',
                filtro: currentTab
            };

            switch(currentTab) {
                case 'fecha':
                    searchData.fechaDesde = document.getElementById('fechaDesde').value;
                    searchData.fechaHasta = document.getElementById('fechaHasta').value;

                    if (!searchData.fechaDesde || !searchData.fechaHasta) {
                        showNotification('Por favor seleccione ambas fechas', 'warning');
                        return;
                    }
                    break;

                case 'autor':
                    searchData.autor = document.getElementById('autor').value.trim();

                    if (!searchData.autor) {
                        showNotification('Por favor ingrese el nombre del autor', 'warning');
                        return;
                    }
                    break;

                case 'titulo':
                    searchData.titulo = document.getElementById('titulo').value.trim();

                    if (!searchData.titulo) {
                        showNotification('Por favor ingrese palabras clave del título', 'warning');
                        return;
                    }
                    break;

                case 'materia':
                    searchData.materia = document.getElementById('materia').value.trim();

                    if (!searchData.materia) {
                        showNotification('Por favor ingrese la materia o tema', 'warning');
                        return;
                    }
                    break;
            }

            // Mostrar datos de búsqueda (temporal)
            console.log('Datos de búsqueda:', searchData);
            showNotification('Búsqueda iniciada. Esta funcionalidad está en desarrollo.', 'info');

            // Aquí se enviará la petición al backend cuando esté implementado
            // fetch('/api/biblioteca_ccb/search', {
            //     method: 'POST',
            //     headers: {'Content-Type': 'application/json'},
            //     body: JSON.stringify(searchData)
            // })
        });
    }

    // Agregar validación de fechas
    const fechaDesde = document.getElementById('fechaDesde');
    const fechaHasta = document.getElementById('fechaHasta');

    if (fechaDesde && fechaHasta) {
        fechaDesde.addEventListener('change', function() {
            fechaHasta.min = this.value;
            if (fechaHasta.value && fechaHasta.value < this.value) {
                fechaHasta.value = this.value;
            }
        });

        fechaHasta.addEventListener('change', function() {
            if (this.value < fechaDesde.value) {
                showNotification('La fecha hasta no puede ser anterior a la fecha desde', 'warning');
                this.value = fechaDesde.value;
            }
        });
    }
});