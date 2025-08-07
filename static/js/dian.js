// static/js/dian_improved.js - Actualizado para soportar ambos scrapers
document.addEventListener('DOMContentLoaded', () => {
  // --- Configuración ---
  const YEAR_START = 2001;  // Cambiado de 2006 a 2001 para incluir años legacy
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

  // --- Referencias DOM ---
  const yearSel = document.getElementById('year');
  const monthSel = document.getElementById('month');
  const searchBtn = document.getElementById('searchButton');
  const resetBtn = document.getElementById('resetButton');
  const previewDiv = document.getElementById('selectionPreview');
  const previewText = document.getElementById('previewText');
  const progressPanel = document.getElementById('progressPanel');
  const finalReport = document.getElementById('finalReport');

  // Referencias a elementos de estadísticas
  const expectedCard = document.getElementById('expectedCard');
  const expectedDocs = document.getElementById('expectedDocs');
  const processedDocs = document.getElementById('processedDocs');
  const downloadedPdfs = document.getElementById('downloadedPdfs');
  const errorCount = document.getElementById('errorCount');
  const duration = document.getElementById('duration');
  const totalSize = document.getElementById('totalSize');
  const processDate = document.getElementById('processDate');
  const statusText = document.getElementById('statusText');

  // Referencias del reporte final
  const finalCollected = document.getElementById('finalCollected');
  const finalDownloaded = document.getElementById('finalDownloaded');
  const finalErrors = document.getElementById('finalErrors');
  const successRate = document.getElementById('successRate');
  const downloadCSV = document.getElementById('downloadCSV');
  const newSearch = document.getElementById('newSearch');

  // Variables de estado
  let currentTimestamp = null;
  let statusInterval = null;
  let durationInterval = null;
  let startTime = null;
  let currentScraperType = null;

  // --- Inicialización ---
  populateYears();
  setupEventListeners();

  function populateYears() {
    for (let y = CURRENT_YEAR; y >= YEAR_START; y--) {
      const opt = document.createElement('option');
      opt.value = y;
      // Añadir indicador visual para años legacy
      if (y <= 2009) {
        opt.textContent = `${y} (archivo histórico)`;
        opt.className = 'legacy-year';
      } else {
        opt.textContent = y;
      }
      yearSel.appendChild(opt);
    }
  }

  function setupEventListeners() {
    yearSel.addEventListener('change', handleYearChange);
    monthSel.addEventListener('change', updatePreview);
    resetBtn.addEventListener('click', resetForm);
    searchBtn.addEventListener('click', startScraping);
    newSearch.addEventListener('click', resetAll);
    downloadCSV.addEventListener('click', downloadCSVFile);
  }

  function handleYearChange() {
    monthSel.innerHTML = '<option value="">-- Mes (opcional) --</option>';
    monthSel.disabled = !yearSel.value;

    if (yearSel.value) {
      const year = parseInt(yearSel.value);
      const maxMonth = year == CURRENT_YEAR
        ? new Date().getMonth() + 1
        : 12;

      MONTHS.forEach(m => {
        if (parseInt(m.value) <= maxMonth) {
          const option = document.createElement('option');
          option.value = m.value;
          option.textContent = m.name;
          monthSel.appendChild(option);
        }
      });

      // Mostrar aviso para años legacy
      if (year <= 2009) {
        showLegacyNotice();
      } else {
        hideLegacyNotice();
      }
    }
    updatePreview();
  }

  function showLegacyNotice() {
    // Buscar o crear el aviso
    let notice = document.getElementById('legacyNotice');
    if (!notice) {
      notice = document.createElement('div');
      notice.id = 'legacyNotice';
      notice.className = 'legacy-notice';
      notice.innerHTML = `
        <i class="fas fa-info-circle"></i>
        <span>Los años 2001-2009 utilizan el sistema de archivo histórico. 
        El procesamiento puede tomar más tiempo debido a la estructura diferente de los documentos.</span>
      `;
      notice.style.cssText = `
        background: #fff3cd;
        border: 1px solid #ffc107;
        color: #856404;
        padding: 12px;
        border-radius: 6px;
        margin: 15px 0;
        display: flex;
        align-items: center;
        gap: 10px;
      `;

      // Insertar después del selector de mes
      const formContainer = monthSel.parentElement.parentElement;
      formContainer.appendChild(notice);
    }
    notice.style.display = 'flex';
  }

  function hideLegacyNotice() {
    const notice = document.getElementById('legacyNotice');
    if (notice) {
      notice.style.display = 'none';
    }
  }

  function updatePreview() {
    if (!yearSel.value) {
      previewDiv.style.display = 'none';
      searchBtn.disabled = true;
      return;
    }

    const year = parseInt(yearSel.value);
    const monthName = monthSel.value
      ? MONTHS.find(m => m.value === monthSel.value).name
      : null;

    let text = monthName
      ? `${monthName} de ${year}`
      : `Todos los meses de ${year}`;

    // Añadir indicador de sistema
    if (year <= 2009) {
      text += ' (Sistema Legacy)';
    } else {
      text += ' (Sistema Moderno)';
    }

    previewText.textContent = text;
    previewDiv.style.display = 'flex';
    searchBtn.disabled = false;
  }

  function resetForm() {
    yearSel.value = '';
    monthSel.innerHTML = '<option value="">-- Primero seleccione un año --</option>';
    monthSel.disabled = true;
    previewDiv.style.display = 'none';
    searchBtn.disabled = true;
    hideLegacyNotice();
  }

  function resetAll() {
    resetForm();
    progressPanel.style.display = 'none';
    finalReport.style.display = 'none';
    clearIntervals();
  }

  function clearIntervals() {
    if (statusInterval) {
      clearInterval(statusInterval);
      statusInterval = null;
    }
    if (durationInterval) {
      clearInterval(durationInterval);
      durationInterval = null;
    }
  }

  async function startScraping() {
    if (!yearSel.value) {
      alert('Por favor seleccione un año');
      return;
    }

    const year = parseInt(yearSel.value);
    currentScraperType = year <= 2009 ? 'legacy' : 'modern';

    // Preparar datos para enviar
    const formData = new FormData();
    formData.append('year', yearSel.value);
    if (monthSel.value) {
      formData.append('month', monthSel.value);
    }

    // Mostrar panel de progreso
    progressPanel.style.display = 'block';
    finalReport.style.display = 'none';

    // Resetear estadísticas
    resetStats();

    // Establecer fecha y hora de inicio
    startTime = Date.now();
    processDate.textContent = new Date().toLocaleString('es-CO');

    // Iniciar contador de duración
    startDurationCounter();

    try {
      // Enviar solicitud al servidor
      const response = await fetch('/dian/start_scraping', {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      if (data.status === 'started') {
        currentTimestamp = data.timestamp;

        // Actualizar texto de estado con información del scraper
        const scraperInfo = data.scraper_type === 'legacy'
          ? 'Sistema Legacy (2001-2009)'
          : 'Sistema Moderno (2010+)';

        statusText.textContent = `Procesando con ${scraperInfo}...`;

        // Calcular documentos esperados según el tipo de scraper
        const monthCount = monthSel.value ? 1 : 12;
        // Los años legacy suelen tener más documentos
        const docsPerMonth = year <= 2009 ? 50 : 10;
        const estimatedDocs = monthCount * docsPerMonth;

        expectedDocs.textContent = estimatedDocs;
        expectedCard.style.display = 'block';

        // Iniciar polling del estado
        statusInterval = setInterval(checkStatus, 2000); // Verificar cada 2 segundos

        // Mostrar mensaje informativo
        showProgressMessage(data.message);
      } else {
        throw new Error(data.message || 'Error al iniciar el proceso');
      }
    } catch (error) {
      console.error('Error:', error);
      alert('Error al iniciar el proceso: ' + error.message);
      progressPanel.style.display = 'none';
      clearIntervals();
    }
  }

  function showProgressMessage(message) {
    // Crear o actualizar mensaje de progreso
    let messageDiv = document.getElementById('progressMessage');
    if (!messageDiv) {
      messageDiv = document.createElement('div');
      messageDiv.id = 'progressMessage';
      messageDiv.style.cssText = `
        background: rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 10px;
        margin-top: 15px;
        text-align: center;
        font-size: 14px;
      `;
      progressPanel.querySelector('.progress-info').appendChild(messageDiv);
    }
    messageDiv.textContent = message;
  }

  async function checkStatus() {
    if (!currentTimestamp) return;

    try {
      const response = await fetch(`/dian/status/${currentTimestamp}`);
      const data = await response.json();

      if (data.status === 'in_progress') {
        // Actualizar estadísticas si están disponibles
        if (data.progress) {
          updateStats(data.progress);
        }
      } else if (data.status === 'completed' || data.status === 'error') {
        clearIntervals();
        showFinalReport(data);
      }
    } catch (error) {
      console.error('Error verificando estado:', error);
    }
  }

  function updateStats(progress) {
    // Mostrar card de documentos esperados solo si hay un valor mayor a 0
    if (progress.expected && progress.expected > 0) {
      expectedCard.style.display = 'block';
      animateNumber(expectedDocs, progress.expected);
    }

    // Actualizar números con animación
    animateNumber(processedDocs, progress.processed || 0);

    // Para el scraper legacy, el campo "downloaded" representa documentos con contenido
    if (currentScraperType === 'legacy') {
      animateNumber(downloadedPdfs, progress.downloaded || 0);
    } else {
      animateNumber(downloadedPdfs, progress.pdfs_downloaded || 0);
    }

    animateNumber(errorCount, progress.errors || 0);

    // Actualizar tamaño total (solo para scraper moderno)
    if (progress.total_size && currentScraperType === 'modern') {
      totalSize.textContent = formatFileSize(progress.total_size);
    } else if (currentScraperType === 'legacy') {
      // Para legacy, mostrar N/A o contar documentos
      totalSize.textContent = 'N/A';
    }

    // Actualizar estado del texto
    if (progress.current_action) {
      statusText.textContent = progress.current_action;
    }

    // Actualizar barra de progreso visual si existe
    updateProgressBar(progress);
  }

  function updateProgressBar(progress) {
    // Crear barra de progreso si no existe
    let progressBar = document.getElementById('visualProgressBar');
    if (!progressBar) {
      const container = document.createElement('div');
      container.style.cssText = `
        background: rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        height: 30px;
        margin: 20px 0;
        overflow: hidden;
        position: relative;
      `;

      progressBar = document.createElement('div');
      progressBar.id = 'visualProgressBar';
      progressBar.style.cssText = `
        background: linear-gradient(90deg, #4ade80 0%, #22c55e 100%);
        height: 100%;
        width: 0%;
        transition: width 0.5s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: bold;
      `;

      container.appendChild(progressBar);
      progressPanel.querySelector('.stats-grid').after(container);
    }

    // Calcular porcentaje
    const expected = progress.expected || 0;
    const processed = progress.processed || 0;
    const percentage = expected > 0 ? Math.min(100, (processed / expected) * 100) : 0;

    progressBar.style.width = `${percentage}%`;
    progressBar.textContent = `${Math.round(percentage)}%`;
  }

  function showFinalReport(data) {
    progressPanel.style.display = 'none';
    finalReport.style.display = 'block';

    const result = data.result || {};

    // Actualizar valores finales
    finalCollected.textContent = result.total_documents || 0;
    finalDownloaded.textContent = result.pdfs_downloaded || result.total_documents || 0;
    finalErrors.textContent = result.errors || 0;

    // Calcular tasa de éxito
    const total = result.total_documents || 0;
    const errors = result.errors || 0;
    const rate = total > 0 ? ((total - errors) / total * 100).toFixed(2) : 0;
    successRate.textContent = `${rate}%`;

    // Mostrar información adicional del scraper usado
    if (result.scraper_type) {
      const scraperTypeDiv = document.createElement('div');
      scraperTypeDiv.style.cssText = `
        text-align: center;
        margin-top: 15px;
        font-size: 14px;
        opacity: 0.9;
      `;
      scraperTypeDiv.textContent = `Procesado con: ${
        result.scraper_type === 'legacy' 
          ? 'Sistema Legacy (2001-2009)' 
          : 'Sistema Moderno (2010+)'
      }`;
      finalReport.querySelector('.report-stats').after(scraperTypeDiv);
    }

    // Guardar timestamp para descargas
    downloadCSV.dataset.timestamp = currentTimestamp;
  }

  function startDurationCounter() {
    durationInterval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      duration.textContent = formatDuration(elapsed);
    }, 1000);
  }

  function resetStats() {
    expectedDocs.textContent = '0';
    processedDocs.textContent = '0';
    downloadedPdfs.textContent = '0';
    errorCount.textContent = '0';
    totalSize.textContent = '0 MB';
    duration.textContent = '0s';
    statusText.textContent = 'Inicializando...';

    // Limpiar elementos adicionales
    const progressMessage = document.getElementById('progressMessage');
    if (progressMessage) {
      progressMessage.remove();
    }

    const progressBar = document.getElementById('visualProgressBar');
    if (progressBar && progressBar.parentElement) {
      progressBar.parentElement.remove();
    }
  }

  function animateNumber(element, newValue) {
    const currentValue = parseInt(element.textContent) || 0;
    if (currentValue !== newValue) {
      element.textContent = newValue;
      element.classList.add('pulse');
      setTimeout(() => element.classList.remove('pulse'), 500);
    }
  }

  function formatDuration(milliseconds) {
    const seconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    } else {
      return `${seconds}s`;
    }
  }

  function formatFileSize(bytes) {
    if (bytes === 0) return '0 MB';
    const mb = bytes / (1024 * 1024);
    return mb.toFixed(2) + ' MB';
  }

  async function downloadCSVFile() {
    const timestamp = downloadCSV.dataset.timestamp;
    if (!timestamp) return;

    window.location.href = `/dian/download_csv/${timestamp}`;
  }
});