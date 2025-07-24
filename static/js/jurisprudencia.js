// jurisprudencia.js - JavaScript específico de la página con mejoras UX

document.addEventListener('DOMContentLoaded', () => {
  // Variables globales
  let currentTimestamp = null;
  let statusInterval = null;
  let isSearching = false;

  // Inicializar componentes
  initializeDatePickers();
  initializeSelects();
  initializeEventListeners();
  createCancelModal(); // NUEVO: Crear modal de cancelación

  /**
   * Configurar selectores de fecha
   */
  function initializeDatePickers() {
    const hoy = new Date();
    const haceUnAno = new Date();
    haceUnAno.setFullYear(haceUnAno.getFullYear() - 1);

    flatpickr('#start-date', {
      dateFormat: 'd/m/Y',
      defaultDate: haceUnAno,
      maxDate: hoy,
      locale: 'es'
    });

    flatpickr('#end-date', {
      dateFormat: 'd/m/Y',
      defaultDate: hoy,
      maxDate: hoy,
      locale: 'es'
    });
  }

  /**
   * Configurar selects con Tom Select
   */
  function initializeSelects() {
    new TomSelect('#sala-select', {
      plugins: ['remove_button'],
      maxItems: null,
      placeholder: 'Seleccione sala(s)…',
      allowEmptyOption: false
    });

    new TomSelect('#providencia-select', {
      maxItems: 1,
      placeholder: 'Seleccione tipo de providencia…',
      allowEmptyOption: false
    });
  }

  /**
   * Configurar event listeners
   */
  function initializeEventListeners() {
    document.getElementById('btn-search').addEventListener('click', handleSearch);
    document.getElementById('btn-check-status').addEventListener('click', checkStatus);
    document.getElementById('btn-cancel-search').addEventListener('click', showCancelModal);
    document.getElementById('btn-new-search').addEventListener('click', newSearch);
    document.getElementById('btn-download-csv').addEventListener('click', downloadCSV);
  }

  /**
   * NUEVO: Crear modal de cancelación
   */
  function createCancelModal() {
    const modalHTML = `
      <div id="cancel-modal" class="modal-overlay" style="display: none;">
        <div class="modal-content">
          <div class="modal-header">
            <i class="fas fa-exclamation-triangle"></i>
            <h3>Confirmar Cancelación</h3>
          </div>
          <div class="modal-body">
            <p>¿Está seguro de cancelar la búsqueda?</p>
            <ul class="cancel-info">
              <li><i class="fas fa-stop-circle"></i> Se detendrá el proceso completamente</li>
              <li><i class="fas fa-trash"></i> Se perderán los resultados no guardados</li>
              <li><i class="fas fa-times"></i> Esta acción no se puede deshacer</li>
            </ul>
          </div>
          <div class="modal-actions">
            <button id="cancel-confirm" class="btn btn-danger">
              <i class="fas fa-stop"></i>
              Sí, Cancelar
            </button>
            <button id="cancel-dismiss" class="btn btn-secondary">
              <i class="fas fa-arrow-left"></i>
              Continuar Búsqueda
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);

    // Event listeners del modal
    document.getElementById('cancel-confirm').addEventListener('click', confirmCancel);
    document.getElementById('cancel-dismiss').addEventListener('click', hideCancelModal);
    document.getElementById('cancel-modal').addEventListener('click', (e) => {
      if (e.target.id === 'cancel-modal') hideCancelModal();
    });
  }

  /**
   * Mostrar modal de cancelación
   */
  function showCancelModal() {
    if (!isSearching || !currentTimestamp) {
      showNotification('No hay búsqueda activa para cancelar', 'warning');
      return;
    }

    document.getElementById('cancel-modal').style.display = 'flex';
  }

  /**
   * Ocultar modal de cancelación
   */
  function hideCancelModal() {
    document.getElementById('cancel-modal').style.display = 'none';
  }

  /**
   * Confirmar cancelación (REAL)
   */
  async function confirmCancel() {
    hideCancelModal();
    showLoader('Cancelando búsqueda...');

    try {
      // Llamar al endpoint de cancelación
      const response = await fetch(`/cancel_scraping/${currentTimestamp}`, {
        method: 'POST'
      });

      const result = await response.json();

      if (response.ok) {
        showNotification('Búsqueda cancelada correctamente', 'success');

        // NUEVO: Recargar página después de 1 segundo
        setTimeout(() => {
          window.location.reload();
        }, 1000);

      } else {
        throw new Error(result.message || 'Error al cancelar');
      }
    } catch (error) {
      console.error('Error cancelando:', error);
      showNotification('Error al cancelar: ' + error.message, 'error');
      hideLoader();
    }
  }

  /**
   * Manejar búsqueda principal
   */
  async function handleSearch() {
    if (isSearching) {
      showNotification('Ya hay una búsqueda en proceso', 'warning');
      return;
    }

    // Bloquear botón y mostrar estado
    setSearchingState(true);
    showLoader('Iniciando búsqueda de jurisprudencia...');

    try {
      const formData = serializeForm();
      const response = await fetch('/start_scraping', {
        method: 'POST',
        body: formData
      });

      const result = await response.json();

      if (response.ok) {
        currentTimestamp = result.timestamp;
        document.getElementById('results-panel').style.display = 'block';
        updateStatusDisplay(result);

        // Consultar estado cada 10 segundos
        if (statusInterval) clearInterval(statusInterval);
        statusInterval = setInterval(() => {
          if (currentTimestamp && isSearching) checkStatus();
        }, 10000);

        showNotification('Búsqueda iniciada correctamente', 'success');
      } else {
        throw new Error(result.message || 'Error en la búsqueda');
      }
    } catch (error) {
      console.error('Error:', error);
      showNotification('Error: ' + error.message, 'error');
      setSearchingState(false);
    }

    hideLoader();
  }

  /**
   * Consultar estado del proceso
   */
  async function checkStatus() {
    if (!currentTimestamp) return;

    try {
      const response = await fetch(`/scraping_status/${currentTimestamp}`);
      const result = await response.json();

      if (response.ok) {
        updateStatusDisplay(result);

        // Si el proceso terminó, desbloquear interfaz
        if (result.final_report) {
          setSearchingState(false);
          showNotification('Búsqueda completada', 'success');
        }
      }
    } catch (error) {
      console.error('Error consultando estado:', error);
    }
  }

  /**
   * Nueva búsqueda - refrescar página
   */
  function newSearch() {
    window.location.reload();
  }

  /**
   * Descargar archivo CSV
   */
  function downloadCSV() {
    if (!currentTimestamp) {
      showNotification('No hay resultados para descargar', 'warning');
      return;
    }

    // Crear enlace de descarga
    const csvUrl = `/download_csv/${currentTimestamp}`;
    const link = document.createElement('a');
    link.href = csvUrl;
    link.download = `jurisprudencia_${currentTimestamp}.csv`;
    link.style.display = 'none';

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showNotification('Descargando archivo CSV...', 'info');
  }

  /**
   * Establecer estado de búsqueda
   */
  function setSearchingState(searching) {
    isSearching = searching;
    const searchBtn = document.getElementById('btn-search');
    const cancelBtn = document.getElementById('btn-cancel-search');
    const newSearchBtn = document.getElementById('btn-new-search');

    if (searching) {
      // Modo búsqueda activa
      searchBtn.disabled = true;
      searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Buscando...';
      searchBtn.classList.add('btn-loading');

      cancelBtn.style.display = 'flex';
      newSearchBtn.style.display = 'none';
    } else {
      // Modo inactivo
      searchBtn.disabled = false;
      searchBtn.innerHTML = '<i class="fas fa-search"></i> Iniciar Búsqueda de Jurisprudencia';
      searchBtn.classList.remove('btn-loading');

      cancelBtn.style.display = 'none';
      newSearchBtn.style.display = 'flex';
    }
  }

  /**
   * Serializar formulario
   */
  function serializeForm() {
    const form = document.getElementById('search-form');
    return new FormData(form);
  }

  /**
   * Mostrar loader
   */
  function showLoader(text = 'Procesando...') {
    document.getElementById('loader-text').textContent = text;
    document.getElementById('loader-overlay').style.display = 'flex';
  }

  /**
   * Ocultar loader
   */
  function hideLoader() {
    document.getElementById('loader-overlay').style.display = 'none';
  }

  /**
   * Actualizar display de estado
   */
  function updateStatusDisplay(data) {
    const content = document.getElementById('status-content');
    const downloadBtn = document.getElementById('btn-download-csv');

    if (data.manifest) {
      const manifest = data.manifest;
      const statusClass = manifest.estado === 'completado' ? 'completed' :
                         manifest.estado === 'cancelado' ? 'error' :
                         manifest.estado === 'ERROR' ? 'error' : 'running';

      let html = `
        <div style="margin-bottom: 1.5rem;">
          <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
            <span class="status-badge status-${statusClass}">
              <i class="fas fa-${statusClass === 'completed' ? 'check-circle' : 
                                statusClass === 'error' ? 'exclamation-circle' : 'clock'}"></i>
              ${manifest.estado}
            </span>
            <small style="color: var(--text-muted);">
              ${new Date(manifest.fecha_busqueda).toLocaleString()}
            </small>
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
            <div>
              <strong>Total esperados:</strong>
              <div style="font-size: 1.5rem; color: var(--accent-primary);">
                ${manifest.total_resultados_esperados}
              </div>
            </div>
          </div>
        </div>
      `;

      if (data.final_report) {
        const report = data.final_report.resumen;
        html += `
          <div style="border-top: 1px solid var(--border); padding-top: 1.5rem;">
            <h4 style="margin-bottom: 1rem; color: var(--text-primary);">
              <i class="fas fa-chart-bar"></i> Reporte Final
            </h4>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem;">
              <div>
                <strong>Recolectados:</strong>
                <div style="font-size: 1.25rem; color: var(--success);">${report.total_recolectados}</div>
              </div>
              <div>
                <strong>Descargados:</strong>
                <div style="font-size: 1.25rem; color: var(--accent-primary);">${report.total_descargados}</div>
              </div>
              <div>
                <strong>Errores:</strong>
                <div style="font-size: 1.25rem; color: var(--error);">${report.total_errores}</div>
              </div>
              <div>
                <strong>Tasa de éxito:</strong>
                <div style="font-size: 1.25rem; color: var(--success);">${report.tasa_exito}</div>
              </div>
            </div>
          </div>
        `;

        // Mostrar botón de descarga cuando termine
        downloadBtn.style.display = 'inline-flex';
      } else {
        // Ocultar botón de descarga mientras está en proceso
        downloadBtn.style.display = 'none';
      }

      content.innerHTML = html;
    } else {
      content.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
          <i class="fas fa-spinner fa-spin" style="font-size: 2rem; color: var(--accent-primary); margin-bottom: 1rem;"></i>
          <p>${data.message || 'Procesando...'}</p>
        </div>
      `;
      downloadBtn.style.display = 'none';
    }
  }

  /**
   * Mostrar notificación
   */
  function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
      <div style="display: flex; align-items: center; gap: 0.5rem;">
        <i class="fas fa-${type === 'error' ? 'exclamation-circle' : 
                          type === 'success' ? 'check-circle' : 
                          type === 'warning' ? 'exclamation-triangle' : 'info-circle'}"></i>
        <span>${message}</span>
      </div>
    `;

    Object.assign(notification.style, {
      position: 'fixed',
      top: '20px',
      right: '20px',
      padding: '1rem 1.5rem',
      borderRadius: '8px',
      color: 'white',
      fontSize: '0.9rem',
      zIndex: '10000',
      background: type === 'error' ? 'var(--error)' :
                  type === 'success' ? 'var(--success)' :
                  type === 'warning' ? 'var(--warning)' : 'var(--accent-primary)',
      boxShadow: 'var(--shadow-lg)',
      transform: 'translateX(100%)',
      transition: 'transform 0.3s ease'
    });

    document.body.appendChild(notification);

    setTimeout(() => {
      notification.style.transform = 'translateX(0)';
    }, 100);

    setTimeout(() => {
      notification.style.transform = 'translateX(100%)';
      setTimeout(() => {
        if (notification.parentNode) {
          notification.parentNode.removeChild(notification);
        }
      }, 300);
    }, 5000);
  }
});