// static/js/dian_improved.js
document.addEventListener('DOMContentLoaded', () => {
  // --- Configuración ---
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

  // --- Inicialización ---
  populateYears();
  setupEventListeners();

  function populateYears() {
    for (let y = CURRENT_YEAR; y >= YEAR_START; y--) {
      const opt = document.createElement('option');
      opt.value = y;
      opt.textContent = y;
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
      const maxMonth = yearSel.value == CURRENT_YEAR
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
    }
    updatePreview();
  }

  function updatePreview() {
    if (!yearSel.value) {
      previewDiv.style.display = 'none';
      searchBtn.disabled = true;
      return;
    }

    const monthName = monthSel.value
      ? MONTHS.find(m => m.value === monthSel.value).name
      : null;

    const text = monthName
      ? `${monthName} de ${yearSel.value}`
      : `Todos los meses de ${yearSel.value}`;

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
        statusText.textContent = 'Procesando...';

        // Calcular documentos esperados (estimación)
        const monthCount = monthSel.value ? 1 : 12;
        const estimatedDocs = monthCount * 8; // Estimación basada en promedio
        expectedDocs.textContent = estimatedDocs;

        // Iniciar polling del estado
        statusInterval = setInterval(checkStatus, 2000); // Verificar cada 2 segundos
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
    animateNumber(downloadedPdfs, progress.pdfs_downloaded || 0);
    animateNumber(errorCount, progress.errors || 0);

    // Actualizar tamaño total
    if (progress.total_size) {
      totalSize.textContent = formatFileSize(progress.total_size);
    }

    // Actualizar estado del texto
    if (progress.current_action) {
      statusText.textContent = progress.current_action;
    }
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