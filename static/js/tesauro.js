// tesauro.js - JavaScript específico para el Tesauro con estilo de jurisprudencia

document.addEventListener('DOMContentLoaded', () => {
  // Variables globales
  let currentTimestamp = null;
  let statusInterval = null;
  let isSearching = false;

  // Inicializar componentes
  initializeDatePickers();
  initializeEventListeners();

  /**
   * Configurar selectores de fecha
   */
  function initializeDatePickers() {
    const hoy = new Date();
    const haceUnAno = new Date();
    haceUnAno.setFullYear(haceUnAno.getFullYear() - 1);

    // Configuración común para ambos datepickers
    const dateConfig = {
      dateFormat: 'Y-m-d', // Formato del tesauro
      maxDate: hoy,
      locale: 'es',
      allowInput: true
    };

    flatpickr('#fecha-desde', {
      ...dateConfig,
      defaultDate: haceUnAno
    });

    flatpickr('#fecha-hasta', {
      ...dateConfig,
      defaultDate: hoy
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

    // Modal de cancelación
    document.getElementById('cancel-confirm').addEventListener('click', confirmCancel);
    document.getElementById('cancel-dismiss').addEventListener('click', hideCancelModal);
    document.getElementById('cancel-modal').addEventListener('click', (e) => {
      if (e.target.id === 'cancel-modal') hideCancelModal();
    });
  }

  /**
   * Toggle opciones avanzadas
   */
  window.toggleAdvanced = function() {
    const options = document.getElementById('advanced-options');
    const icon = document.getElementById('advanced-icon');

    if (options.style.display === 'none' || options.style.display === '') {
      options.style.display = 'block';
      icon.classList.remove('fa-chevron-right');
      icon.classList.add('fa-chevron-down');
    } else {
      options.style.display = 'none';
      icon.classList.remove('fa-chevron-down');
      icon.classList.add('fa-chevron-right');
    }
  };

  /**
   * Vista previa de búsqueda
   */
  window.previewSearch = async function() {
    showLoader('Obteniendo vista previa...');

    try {
      const formData = serializeForm();
      const response = await fetch('/tesauro/preview', {
        method: 'POST',
        body: formData
      });

      const result = await response.json();

      if (response.ok) {
        displayPreview(result);
      } else {
        showNotification('Error: ' + result.message, 'error');
      }
    } catch (error) {
      console.error('Error:', error);
      showNotification('Error al obtener vista previa', 'error');
    }

    hideLoader();
  };

  /**
   * Mostrar vista previa
   */
  function displayPreview(data) {
    const panel = document.getElementById('preview-panel');
    const content = document.getElementById('preview-content');

    panel.style.display = 'block';

    if (data.preview && data.preview.length > 0) {
      let html = `<p style="margin-bottom: 1rem; color: var(--text-muted);">${data.message}</p>`;

      data.preview.forEach(doc => {
        html += `
          <div class="preview-item">
            <div class="preview-title">${doc.titulo || 'Sin título'}</div>
            <div class="preview-meta">
              <span><i class="fas fa-tags"></i> ${doc.tipo_contenido}</span>
              <span><i class="fas fa-calendar"></i> ${doc.fecha_sentencia || 'Sin fecha'}</span>
              <span><i class="fas fa-hashtag"></i> ${doc.numero_radicado || 'Sin número'}</span>
            </div>
            ${doc.tema ? `<div style="margin-top: 0.5rem; font-size: 0.875rem; color: var(--text-secondary);">
              <strong>Tema:</strong> ${doc.tema}
            </div>` : ''}
          </div>
        `;
      });

      content.innerHTML = html;
    } else {
      content.innerHTML = '<p style="text-align: center; color: var(--text-muted);">No se encontraron documentos con los filtros especificados.</p>';
    }

    // Scroll suave hacia la vista previa
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  /**
   * Manejar búsqueda principal
   */
  async function handleSearch() {
    if (isSearching) {
      showNotification('Ya hay una búsqueda en proceso', 'warning');
      return;
    }

    // Validar que al menos haya un filtro
    const formData = serializeForm();
    const hasFilters = formData.get('tipo_contenido') ||
                      formData.get('fecha_desde') ||
                      formData.get('fecha_hasta');

    if (!hasFilters) {
      showNotification('Por favor seleccione al menos un filtro', 'warning');
      return;
    }

    // Bloquear botón y mostrar estado
    setSearchingState(true);
    showLoader('Iniciando búsqueda en el Tesauro Jurídico...');

    try {
      // Asegurar que el checkbox se envíe correctamente
      const downloadPdfs = document.getElementById('download-pdfs').checked;
      formData.set('download_pdfs', downloadPdfs ? 'true' : 'false');

      const response = await fetch('/tesauro/start_scraping', {
        method: 'POST',
        body: formData
      });

      const result = await response.json();

      if (response.ok) {
        currentTimestamp = result.timestamp;
        document.getElementById('results-panel').style.display = 'block';
        document.getElementById('preview-panel').style.display = 'none';
        updateStatusDisplay(result);

        // Consultar estado cada 5 segundos
        if (statusInterval) clearInterval(statusInterval);
        statusInterval = setInterval(() => {
          if (currentTimestamp && isSearching) checkStatus();
        }, 5000);

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
      const response = await fetch(`/tesauro/status/${currentTimestamp}`);
      const result = await response.json();

      if (response.ok) {
        updateStatusDisplay(result);

        // Si el proceso terminó, desbloquear interfaz
        if (result.final_report) {
          setSearchingState(false);
          showNotification('Búsqueda completada', 'success');
          if (statusInterval) {
            clearInterval(statusInterval);
            statusInterval = null;
          }
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
    const csvUrl = `/tesauro/download_csv/${currentTimestamp}`;
    const link = document.createElement('a');
    link.href = csvUrl;
    link.download = `tesauro_${currentTimestamp}.csv`;
    link.style.display = 'none';

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showNotification('Descargando archivo CSV...', 'info');
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
   * Confirmar cancelación
   */
  async function confirmCancel() {
    hideCancelModal();
    showLoader('Cancelando búsqueda...');

    try {
      const response = await fetch(`/tesauro/cancel_scraping/${currentTimestamp}`, {
        method: 'POST'
      });

      const result = await response.json();

      if (response.ok) {
        showNotification('Búsqueda cancelada correctamente', 'success');

        // Recargar página después de 1 segundo
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
   * Establecer estado de búsqueda
   */
  function setSearchingState(searching) {
    isSearching = searching;
    const searchBtn = document.getElementById('btn-search');
    const cancelBtn = document.getElementById('btn-cancel-search');
    const newSearchBtn = document.getElementById('btn-new-search');
    const previewBtn = document.getElementById('btn-preview');

    if (searching) {
      // Modo búsqueda activa
      searchBtn.disabled = true;
      searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Buscando...';
      searchBtn.classList.add('btn-loading');

      previewBtn.disabled = true;
      previewBtn.classList.add('btn-loading');

      cancelBtn.style.display = 'flex';
      newSearchBtn.style.display = 'none';
    } else {
      // Modo inactivo
      searchBtn.disabled = false;
      searchBtn.innerHTML = '<i class="fas fa-search"></i> Iniciar Búsqueda Completa';
      searchBtn.classList.remove('btn-loading');

      previewBtn.disabled = false;
      previewBtn.classList.remove('btn-loading');

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

    if (data.final_report) {
      // Proceso completado
      const report = data.final_report;
      const html = `
        <div style="border-radius: var(--border-radius); padding: 1.5rem; background: var(--bg-input);">
          <h4 style="margin-bottom: 1rem; color: var(--text-primary);">
            <i class="fas fa-check-circle" style="color: var(--success);"></i> Proceso Completado
          </h4>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem;">
            <div>
              <strong>Total documentos:</strong>
              <div style="font-size: 1.25rem; color: var(--accent-primary);">${report.resumen.total_documentos}</div>
            </div>
            <div>
              <strong>PDFs descargados:</strong>
              <div style="font-size: 1.25rem; color: var(--success);">${report.resumen.pdfs_descargados}</div>
            </div>
            <div>
              <strong>Errores:</strong>
              <div style="font-size: 1.25rem; color: var(--error);">${report.resumen.errores_descarga}</div>
            </div>
            <div>
              <strong>Tasa de éxito:</strong>
              <div style="font-size: 1.25rem; color: var(--success);">${report.resumen.tasa_exito}</div>
            </div>
          </div>
          <div style="margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid var(--border);">
            <strong>Duración:</strong> ${report.duracion_segundos.toFixed(2)} segundos
          </div>
        </div>
      `;

      content.innerHTML = html;
      downloadBtn.style.display = 'inline-flex';
    } else if (data.parametros) {
      // Proceso iniciado
      let html = `
        <div style="margin-bottom: 1.5rem;">
          <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
            <span class="status-badge status-running">
              <i class="fas fa-spinner fa-spin"></i>
              Procesando
            </span>
            <small style="color: var(--text-muted);">
              ${new Date().toLocaleString()}
            </small>
          </div>
          <div style="background: var(--bg-input); padding: 1rem; border-radius: var(--border-radius);">
            <h5 style="margin-bottom: 0.5rem;">Parámetros de búsqueda:</h5>
            <ul style="list-style: none; padding: 0; margin: 0; font-size: 0.875rem;">
      `;

      if (data.parametros.filtros.tipo_contenido) {
        html += `<li><i class="fas fa-tags"></i> Tipo: ${data.parametros.filtros.tipo_contenido}</li>`;
      }
      if (data.parametros.filtros.fecha_desde || data.parametros.filtros.fecha_hasta) {
        html += `<li><i class="fas fa-calendar"></i> Fechas: ${data.parametros.filtros.fecha_desde || 'Inicio'} - ${data.parametros.filtros.fecha_hasta || 'Fin'}</li>`;
      }
      html += `
              <li><i class="fas fa-download"></i> Descargar PDFs: ${data.parametros.download_pdfs ? 'Sí' : 'No'}</li>
              <li><i class="fas fa-users"></i> Workers: ${data.parametros.max_workers}</li>
            </ul>
          </div>
        </div>
      `;

      // Mostrar últimas líneas del log si están disponibles
      if (data.log_tail && data.log_tail.length > 0) {
        const lastLines = data.log_tail.slice(-5).map(line =>
          line.replace(/\n/g, '').substring(0, 100)
        ).join('<br>');

        html += `
          <div style="margin-top: 1rem; background: var(--bg-secondary); padding: 1rem; border-radius: var(--border-radius);">
            <h5 style="margin-bottom: 0.5rem; font-size: 0.875rem;">Actividad reciente:</h5>
            <div style="font-family: monospace; font-size: 0.75rem; color: var(--text-muted);">
              ${lastLines}
            </div>
          </div>
        `;
      }

      content.innerHTML = html;
      downloadBtn.style.display = 'none';
    } else {
      // Estado desconocido
      content.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
          <i class="fas fa-spinner fa-spin" style="font-size: 2rem; color: var(--accent-primary); margin-bottom: 1rem;"></i>
          <p>Procesando...</p>
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