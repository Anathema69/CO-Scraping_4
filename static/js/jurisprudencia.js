// jurisprudencia.js - JavaScript específico de la página

document.addEventListener('DOMContentLoaded', () => {
  // Variables globales
  let currentTimestamp = null;
  let statusInterval = null;

  // Inicializar componentes
  initializeDatePickers();
  initializeSelects();
  initializeEventListeners();

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
    document.getElementById('btn-view-logs').addEventListener('click', viewLogs);
  }

  /**
   * Manejar búsqueda principal
   */
  async function handleSearch() {
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
          if (currentTimestamp) checkStatus();
        }, 10000);

      } else {
        throw new Error(result.message || 'Error en la búsqueda');
      }
    } catch (error) {
      console.error('Error:', error);
      showNotification('Error: ' + error.message, 'error');
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
      }
    } catch (error) {
      console.error('Error consultando estado:', error);
    }
  }

  /**
   * Ver logs del proceso
   */
  function viewLogs() {
    if (currentTimestamp) {
      const logUrl = `/logs/${currentTimestamp}/descarga.log`;
      window.open(logUrl, '_blank');
    } else {
      showNotification('No hay proceso activo', 'warning');
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

    if (data.manifest) {
      const manifest = data.manifest;
      const statusClass = manifest.estado === 'COMPLETADO' ? 'completed' :
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
      }

      content.innerHTML = html;
    } else {
      content.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
          <i class="fas fa-spinner fa-spin" style="font-size: 2rem; color: var(--accent-primary); margin-bottom: 1rem;"></i>
          <p>${data.message || 'Procesando...'}</p>
        </div>
      `;
    }
  }

  /**
   * Mostrar notificación
   */
  function showNotification(message, type = 'info') {
    // Crear elemento de notificación
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

    // Estilos de notificación
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

    // Animar entrada
    setTimeout(() => {
      notification.style.transform = 'translateX(0)';
    }, 100);

    // Remover después de 5 segundos
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