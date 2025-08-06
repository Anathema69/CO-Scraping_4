// Biblioteca Digital CCB - Funcionalidad actualizada con búsqueda por autor

// Variables globales
let currentTab = 'fecha';
let searchInProgress = false;
let progressInterval = null;
let authorsCache = null;

// Inicializar años disponibles
function initializeYears() {
    const yearSelect = document.getElementById('yearFilter');
    const currentYear = new Date().getFullYear();

    // Agregar años desde 2000 hasta el año actual
    for (let year = currentYear; year >= 2000; year--) {
        const option = document.createElement('option');
        option.value = year.toString();
        option.textContent = year;
        yearSelect.appendChild(option);
    }
}

// Inicializar campo de autor con autocompletado
async function initializeAuthorField() {
    const autorInput = document.getElementById('autor');
    const autorDatalist = document.getElementById('autorList');

    // Cargar lista de autores cuando el usuario empiece a escribir
    autorInput.addEventListener('input', async function(e) {
        const value = e.target.value;

        // Solo buscar si hay al menos 2 caracteres
        if (value.length < 2) {
            autorDatalist.innerHTML = '';
            return;
        }

        // Si no tenemos cache, cargar autores
        if (!authorsCache) {
            showNotification('Cargando lista de autores...', 'info');
            try {
                const response = await fetch('/api/biblioteca_ccb/authors');
                const data = await response.json();
                if (data.status === 'success') {
                    authorsCache = data.authors;
                }
            } catch (error) {
                console.error('Error cargando autores:', error);
                return;
            }
        }

        // Filtrar autores que coincidan
        const filtered = authorsCache.filter(author =>
            author.nombre.toLowerCase().includes(value.toLowerCase())
        ).slice(0, 20); // Limitar a 20 sugerencias

        // Actualizar datalist
        autorDatalist.innerHTML = '';
        filtered.forEach(author => {
            const option = document.createElement('option');
            option.value = author.nombre;
            option.textContent = `(${author.cantidad} documentos)`;
            autorDatalist.appendChild(option);
        });
    });
}

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
            select.value = 'nacional';
            socialNotice.style.display = 'none';
            handleArbitrageTypeChange();
        }, 3000);
    } else {
        filtersCard.style.display = 'none';
        socialNotice.style.display = 'none';
    }
}

// Manejar cambio de año
function handleYearChange() {
    const yearSelect = document.getElementById('yearFilter');
    const monthSelect = document.getElementById('monthFilter');
    const monthFormText = monthSelect.nextElementSibling;

    if (yearSelect.value) {
        monthSelect.disabled = false;
        monthFormText.textContent = 'Seleccione el mes (opcional)';
    } else {
        monthSelect.disabled = true;
        monthSelect.value = '';
        monthFormText.textContent = 'Primero seleccione un año';
    }
}

// Cambiar pestaña activa
function setActiveTab(button, tabName) {
    // Limpiar campos de la pestaña actual antes de cambiar
    clearCurrentTabFields();

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

    // Resetear selector de mes
    const monthSelect = document.getElementById('monthFilter');
    monthSelect.disabled = true;
    monthSelect.nextElementSibling.textContent = 'Primero seleccione un año';

    // Ocultar panel de resultados
    document.getElementById('resultsPanel').style.display = 'none';

    // Habilitar botón de búsqueda
    document.getElementById('searchButton').disabled = false;

    showNotification('Filtros limpiados correctamente', 'info');
}

// Formatear bytes a tamaño legible
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Formatear duración
function formatDuration(seconds) {
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${minutes}m ${secs}s`;
}

// Actualizar estadísticas
function updateStats(data) {
    // Actualizar contadores
    let expected = data.expected || 0;

    // Si expected es -1 o 0, mostrar "Calculando..." o el valor procesado
    if (expected <= 0 && data.processed > 0) {
        expected = data.processed + '...';
    } else if (expected <= 0) {
        expected = 'Calculando...';
    }

    document.getElementById('expectedCount').textContent = expected;
    document.getElementById('processedCount').textContent = data.processed || 0;
    document.getElementById('downloadedCount').textContent = data.downloaded || 0;
    document.getElementById('failedCount').textContent = data.failed || 0;

    // Si la búsqueda terminó
    if (data.status === 'completed') {
        clearInterval(progressInterval);
        searchInProgress = false;

        // Actualizar expected con el valor final si era "Calculando..."
        if (typeof expected === 'string') {
            document.getElementById('expectedCount').textContent = data.stats.expected || data.stats.processed || 0;
        }

        // Ocultar spinner
        document.getElementById('searchStatus').style.display = 'none';

        // Mostrar detalles
        document.getElementById('resultDetails').style.display = 'block';
        document.getElementById('duration').textContent = formatDuration(data.duration || 0);
        document.getElementById('totalSize').textContent = formatBytes(data.total_size || 0);
        document.getElementById('searchDate').textContent = new Date().toLocaleString('es-CO');

        // Mostrar reporte final
        document.getElementById('finalReport').style.display = 'block';
        document.getElementById('summaryCollected').textContent = data.stats.expected || data.stats.processed || 0;
        document.getElementById('summaryDownloaded').textContent = data.stats.downloaded || 0;
        document.getElementById('summaryErrors').textContent = data.stats.failed || 0;

        const successRate = data.stats.success_rate || 0;
        document.getElementById('successRate').textContent = successRate.toFixed(2) + '%';

        // Cambiar color según tasa de éxito
        const successRateElement = document.getElementById('successRate');
        if (successRate >= 90) {
            successRateElement.className = 'summary-value success-text';
        } else if (successRate >= 70) {
            successRateElement.className = 'summary-value warning-text';
        } else {
            successRateElement.className = 'summary-value error-text';
        }

        // Mostrar notificación
        if (data.stats.failed > 0) {
            showNotification(`Búsqueda completada con ${data.stats.failed} errores`, 'warning');
        } else {
            showNotification('Búsqueda completada exitosamente', 'success');
        }

        // Habilitar botón de búsqueda
        document.getElementById('searchButton').disabled = false;
    }
}

// Obtener progreso de búsqueda
async function getSearchProgress() {
    try {
        const response = await fetch('/api/biblioteca_ccb/progress');
        const data = await response.json();

        if (data.in_progress) {
            updateStats(data);
        }
    } catch (error) {
        console.error('Error obteniendo progreso:', error);
    }
}


// Verificar si la búsqueda terminó
async function checkSearchCompletion() {
    try {
        const response = await fetch('/api/biblioteca_ccb/status');
        const data = await response.json();

        if (data.status === 'completed') {
            updateStats(data);
        } else {
            // Seguir verificando
            setTimeout(checkSearchCompletion, 3000);
        }
    } catch (error) {
        console.error('Error verificando estado:', error);
    }
}

// Manejar envío del formulario
document.addEventListener('DOMContentLoaded', function() {
    console.log('Biblioteca CCB: DOM cargado');

    // Inicializar años
    initializeYears();

    // Inicializar campo de autor
    initializeAuthorField();

    // Auto-seleccionar la opción nacional al cargar
    const tipoArbitraje = document.getElementById('tipoArbitraje');
    if (tipoArbitraje && tipoArbitraje.value === 'nacional') {
        console.log('Biblioteca CCB: Auto-seleccionando arbitraje nacional');
        handleArbitrageTypeChange();
    }

    const form = document.getElementById('searchForm');
    console.log('Biblioteca CCB: Formulario encontrado:', form);

    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            console.log('Biblioteca CCB: Submit detectado');

            if (searchInProgress) {
                showNotification('Ya hay una búsqueda en progreso', 'warning');
                return;
            }

            // Recopilar datos según la pestaña activa
            let searchData = {
                tipo: 'arbitraje_nacional',
                filtro: currentTab
            };

            console.log('Biblioteca CCB: Tab actual:', currentTab);

            switch(currentTab) {
                case 'fecha':
                    const year = document.getElementById('yearFilter').value;
                    const month = document.getElementById('monthFilter').value;

                    console.log('Biblioteca CCB: Año:', year, 'Mes:', month);

                    // Construir filtro de fecha
                    if (year && month) {
                        searchData.date_filter = `${year}-${month}`;
                    } else if (year) {
                        searchData.date_filter = year;
                    }
                    // Si no hay filtros, se descargará todo

                    break;

                case 'autor':
                    searchData.autor = document.getElementById('autor').value.trim();
                    if (!searchData.autor) {
                        showNotification('Por favor ingrese el nombre del autor', 'warning');
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

                case 'titulo':
                    searchData.titulo = document.getElementById('titulo').value.trim();
                    if (!searchData.titulo) {
                        showNotification('Por favor ingrese palabras clave del título', 'warning');
                        return;
                    }
                    break;
            }

            // Confirmar si no hay filtros
            if (currentTab === 'fecha' && !searchData.date_filter) {
                const confirmDownload = confirm(
                    '¿Está seguro de que desea descargar TODOS los documentos disponibles?\n\n' +
                    'Esto puede tomar mucho tiempo y espacio en disco.'
                );

                if (!confirmDownload) {
                    return;
                }
            }

            // Iniciar búsqueda
            console.log('Biblioteca CCB: Iniciando búsqueda con:', searchData);
            await startSearchEnhanced(searchData);
        });
    } else {
        console.error('Biblioteca CCB: No se encontró el formulario searchForm');
    }
});

// Función para mostrar notificaciones (debe estar definida en el archivo principal)
function showNotification(message, type) {
    // Si existe la función global, usarla
    if (typeof window.showNotification === 'function') {
        window.showNotification(message, type);
    } else {
        // Implementación básica de notificación
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 1rem 1.5rem;
            background: ${type === 'success' ? '#48bb78' : type === 'error' ? '#f56565' : '#00d4ff'};
            color: white;
            border-radius: 6px;
            z-index: 1000;
            animation: slideIn 0.3s ease;
        `;
        notification.textContent = message;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

    // Log en consola para debugging
    console.log(`[${type.toUpperCase()}] ${message}`);
}

// Agregar estas funciones al archivo biblioteca_ccb.js

// Variable global para almacenar autores encontrados
let foundAuthors = [];

// Función para mostrar modal de selección de autores
function showAuthorSelectionModal(authors, originalQuery) {
    showSelectionModal(authors, originalQuery, 'autor');
}

// Función para cerrar el modal
function closeAuthorModal() {
    closeSelectionModal();
}

// Función para seleccionar un autor
async function selectAuthor(index) {
    await selectItem(index, 'autor');
}

function showSearchingLoader(message = 'Buscando coincidencias...') {
    const loaderHTML = `
        <div id="searchingLoader" style="
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: var(--bg-card);
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
            z-index: 3000;
            text-align: center;
            min-width: 300px;
        ">
            <div style="
                width: 48px;
                height: 48px;
                border: 4px solid var(--bg-input);
                border-top-color: var(--accent-primary);
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 0 auto 1rem;
            "></div>
            <p style="color: var(--text-primary); margin: 0; font-size: 1.1rem;">${message}</p>
        </div>
        <div id="searchingOverlay" style="
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(15, 23, 42, 0.6);
            backdrop-filter: blur(2px);
            z-index: 2999;
        "></div>
        <style>
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
        </style>
    `;

    document.body.insertAdjacentHTML('beforeend', loaderHTML);
}

// Función para ocultar loader de búsqueda
function hideSearchingLoader() {
    const loader = document.getElementById('searchingLoader');
    const overlay = document.getElementById('searchingOverlay');
    if (loader) loader.remove();
    if (overlay) overlay.remove();
}

// Función para limpiar campos según la pestaña activa
function clearCurrentTabFields() {
    switch(currentTab) {
        case 'fecha':
            document.getElementById('yearFilter').value = '';
            document.getElementById('monthFilter').value = '';
            document.getElementById('monthFilter').disabled = true;
            document.getElementById('monthFilter').nextElementSibling.textContent = 'Primero seleccione un año';
            break;
        case 'autor':
            document.getElementById('autor').value = '';
            break;
        case 'materia':
            document.getElementById('materia').value = '';
            break;
        case 'titulo':
            document.getElementById('titulo').value = '';
            break;
    }
}

function showSelectionModal(items, originalQuery, type = 'autor') {
    // Validar que los items tengan la estructura correcta
    console.log('showSelectionModal llamado con:', {
        itemsLength: items.length,
        type: type,
        originalQuery: originalQuery,
        primerItem: items[0]
    });

    // Filtrar items válidos
    const validItems = items.filter(item => item && item.nombre);

    if (validItems.length === 0) {
        console.error('No hay items válidos para mostrar');
        showNotification('Error: No se recibieron datos válidos del servidor', 'error');
        closeSelectionModal();
        return;
    }

    let titleText, itemsText, iconClass;

    switch(type) {
        case 'materia':
            titleText = 'Seleccione una materia';
            itemsText = 'materias';
            iconClass = 'tags';
            break;
        case 'titulo':
            titleText = 'Seleccione un título';
            itemsText = 'títulos';
            iconClass = 'file-alt';
            break;
        default:
            titleText = 'Seleccione un autor';
            itemsText = 'autores';
            iconClass = 'users';
    }

    const modalHTML = `
        <div id="selectionModal" class="modal-overlay" style="display: flex;">
            <div class="modal-content" style="max-width: 700px;">
                <div class="modal-header">
                    <i class="fas fa-${iconClass}"></i>
                    <h3>${titleText}</h3>
                </div>
                <div class="modal-body">
                    <p>Se encontraron ${validItems.length} ${itemsText} que coinciden con "<strong>${originalQuery}</strong>".</p>
                    <p>Por favor, seleccione ${type === 'materia' ? 'la materia específica' : 
                                             type === 'titulo' ? 'el título específico' : 
                                             'el autor específico'} que desea buscar:</p>
                    
                    <div class="item-list" style="max-height: 400px; overflow-y: auto; margin-top: 1rem;">
                        ${validItems.map((item, index) => {
                            // Validar cada item individualmente
                            const itemName = item.nombre || 'Sin nombre';
                            const itemCount = item.cantidad || 0;
                            
                            return `
                            <div class="selection-item" style="
                                padding: 1rem;
                                margin-bottom: 0.5rem;
                                background: var(--bg-input);
                                border-radius: 8px;
                                cursor: pointer;
                                transition: all 0.3s ease;
                                display: flex;
                                justify-content: space-between;
                                align-items: center;
                                ${type === 'titulo' ? 'flex-direction: column; align-items: stretch;' : ''}
                            " onclick="selectItem(${index}, '${type}')">
                                <div style="${type === 'titulo' ? 'margin-bottom: 0.5rem;' : ''}">
                                    <strong style="${type === 'titulo' ? 'font-size: 0.95rem; line-height: 1.4;' : ''}">${itemName}</strong>
                                </div>
                                <div style="display: flex; align-items: center; gap: 0.5rem; ${type === 'titulo' ? 'align-self: flex-end;' : ''}">
                                    <span class="badge" style="
                                        background: var(--accent-primary);
                                        color: var(--bg-primary);
                                        padding: 0.25rem 0.75rem;
                                        border-radius: 20px;
                                        font-size: 0.875rem;
                                    ">${itemCount} documento${itemCount !== 1 ? 's' : ''}</span>
                                    <i class="fas fa-chevron-right" style="color: var(--text-secondary);"></i>
                                </div>
                            </div>
                        `}).join('')}
                    </div>
                </div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeSelectionModal()">
                        <i class="fas fa-times"></i>
                        Cancelar
                    </button>
                </div>
            </div>
        </div>
    `;

    // Agregar estilos hover
    const style = document.createElement('style');
    style.textContent = `
        .selection-item:hover {
            background: var(--bg-secondary) !important;
            transform: translateX(4px);
        }
        .item-list::-webkit-scrollbar {
            width: 8px;
        }
        .item-list::-webkit-scrollbar-track {
            background: var(--bg-secondary);
            border-radius: 4px;
        }
        .item-list::-webkit-scrollbar-thumb {
            background: var(--border-color);
            border-radius: 4px;
        }
        .item-list::-webkit-scrollbar-thumb:hover {
            background: var(--accent-primary);
        }
    `;
    document.head.appendChild(style);

    // Insertar modal en el DOM
    document.body.insertAdjacentHTML('beforeend', modalHTML);

     // Guardar items válidos en variable global
    foundAuthors = validItems;
}

// Función para cerrar el modal de selección
function closeSelectionModal() {
    const modal = document.getElementById('selectionModal');
    if (modal) {
        modal.remove();
    }
    foundAuthors = [];

    // Habilitar botón de búsqueda
    document.getElementById('searchButton').disabled = false;
}

// Función para seleccionar un item (autor o materia)
async function selectItem(index, type = 'autor') {
    const selectedItem = foundAuthors[index];

    // Cerrar modal
    closeSelectionModal();

    // Actualizar el campo de entrada con el item seleccionado
    switch(type) {
        case 'materia':
            document.getElementById('materia').value = selectedItem.nombre;
            break;
        case 'titulo':
            document.getElementById('titulo').value = selectedItem.nombre;
            break;
        default:
            document.getElementById('autor').value = selectedItem.nombre;
    }

    // Iniciar búsqueda con el item exacto
    const searchData = {
        tipo: 'arbitraje_nacional',
        filtro: type,
        [type]: selectedItem.nombre
    };

    console.log(`Biblioteca CCB: Buscando con ${type} exacto:`, selectedItem.nombre);
    await startSearchEnhanced(searchData);
}
async function startSearchEnhanced(searchData) {
    console.log('startSearchEnhanced llamada con:', searchData);
    searchInProgress = true;

    // Deshabilitar botón de búsqueda
    document.getElementById('searchButton').disabled = true;

    // Mostrar loader si es búsqueda por autor o materia
    if (searchData.filtro === 'autor' || searchData.filtro === 'materia' || searchData.filtro === 'titulo') {
    let searchingText = searchData.filtro === 'autor' ? 'autores' :
                       searchData.filtro === 'materia' ? 'materias' : 'títulos';
    showSearchingLoader(`Buscando ${searchingText}...`);
    }

    try {
        console.log('Enviando petición a /api/biblioteca_ccb/search');
        const response = await fetch('/api/biblioteca_ccb/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(searchData)
        });

        console.log('Respuesta recibida:', response.status);
        const result = await response.json();
        console.log('Resultado:', result);

        // Ocultar loader
        hideSearchingLoader();

        if (result.status === 'multiple_matches') {
			// Agregar este log para verificar qué datos están llegando
			console.log('Datos de matches recibidos:', JSON.stringify(result.matches, null, 2));
			console.log('Tipo de match:', result.type);


			// Verificar que cada match tenga la estructura correcta
			result.matches.forEach((match, index) => {
				console.log(`Match ${index}:`, {
					nombre: match.nombre,
					cantidad: match.cantidad,
					tieneNombre: !!match.nombre
				});
			});

            // Mostrar modal de selección
			searchInProgress = false;
			const matchType = result.type || searchData.filtro;
			showSelectionModal(result.matches, result.query, matchType);
            searchInProgress = false;



            const itemText = matchType === 'materia' ? 'materias' : 'autores';
            showNotification(`Se encontraron ${result.matches.length} ${itemText}. Por favor seleccione uno.`, 'info');
            return;
        } else if (result.status === 'no_matches') {
            // No se encontraron coincidencias
            console.log('No se encontraron coincidencias');
            searchInProgress = false;
            document.getElementById('searchButton').disabled = false;

            const itemText = searchData.filtro === 'materia' ? 'materias' : 'autores';
            showNotification(`No se encontraron ${itemText} con ese nombre`, 'warning');
            return;
        } else if (!response.ok) {
            console.error('Error en respuesta:', result);
            throw new Error(result.error || `Error HTTP: ${response.status}`);
        }

        console.log('Iniciando búsqueda normal...');

        // Continuar con el proceso normal de búsqueda
        // Mostrar panel de resultados
        const resultsPanel = document.getElementById('resultsPanel');
        resultsPanel.style.display = 'block';
        resultsPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });

        // Resetear vista
        document.getElementById('searchStatus').style.display = 'flex';
        document.getElementById('statsGrid').style.display = 'grid';
        document.getElementById('resultDetails').style.display = 'none';
        document.getElementById('finalReport').style.display = 'none';

        // Resetear estadísticas
        updateStats({
            expected: 0,
            processed: 0,
            downloaded: 0,
            failed: 0
        });

        // Iniciar polling de progreso
        progressInterval = setInterval(getSearchProgress, 2000);

        // Esperar a que termine
        checkSearchCompletion();

    } catch (error) {
        console.error('Error iniciando búsqueda:', error);
        hideSearchingLoader();
        showNotification('Error al iniciar la búsqueda: ' + error.message, 'error');
        searchInProgress = false;
        document.getElementById('searchButton').disabled = false;
        document.getElementById('searchStatus').style.display = 'none';
    }
}


