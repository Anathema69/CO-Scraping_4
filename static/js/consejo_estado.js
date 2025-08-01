// consejo_estado.js

document.addEventListener("DOMContentLoaded", () => {
  let currentTimestamp = null;
  let statusInterval = null;
  let isSearching = false;

  // Inicializar datepickers
  flatpickr("#fecha-desde", { locale: "es", dateFormat: "d/m/Y" });
  flatpickr("#fecha-hasta", { locale: "es", dateFormat: "d/m/Y" });

  // Listeners
  document.getElementById("btn-search").addEventListener("click", handleSearch);
  document.getElementById("btn-check-status").addEventListener("click", checkStatus);
  document.getElementById("btn-download-manifest").addEventListener("click", downloadManifest);
  document.getElementById("btn-download-csv").addEventListener("click", downloadCSV);
  document.getElementById("btn-cancel-search").addEventListener("click", cancelSearch);
  document.getElementById("btn-new-search").addEventListener("click", newSearch);

  function setSearchingState(on) {
    isSearching = on;
    const searchBtn = document.getElementById("btn-search");
    const cancelBtn = document.getElementById("btn-cancel-search");
    const newSearchBtn = document.getElementById("btn-new-search");

    if (on) {
      searchBtn.disabled = true;
      searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Buscando...';
      searchBtn.classList.add("btn-loading");
      cancelBtn.style.display = "inline-flex";
      newSearchBtn.style.display = "none";
    } else {
      searchBtn.disabled = false;
      searchBtn.innerHTML = '<i class="fas fa-search"></i> Iniciar Búsqueda';
      searchBtn.classList.remove("btn-loading");
      cancelBtn.style.display = "none";
      newSearchBtn.style.display = "inline-flex";
    }
  }

  async function handleSearch() {
    if (isSearching) return;

    const sala = document.getElementById("sala-decision").value.trim();
    const desde = document.getElementById("fecha-desde").value.trim();
    const hasta = document.getElementById("fecha-hasta").value.trim();

    if (!sala || !desde || !hasta) {
      showNotification("Por favor completa todos los campos requeridos", "warning");
      return;
    }

    setSearchingState(true);
    showLoader("Iniciando búsqueda en el Consejo de Estado...");
    document.getElementById("results-panel").style.display = "block";

    const formData = new FormData();
    formData.append("sala_decision", sala);
    formData.append("fecha_desde", desde);
    formData.append("fecha_hasta", hasta);
    formData.append("max_workers", document.getElementById("max-workers").value || "3");
    formData.append("download_pdfs", "true");

    try {
      const resp = await fetch("/consejo_estado/start_scraping", {
        method: "POST",
        body: formData
      });

      const result = await resp.json();

      if (!resp.ok) {
        throw new Error(result.message || `HTTP ${resp.status}`);
      }

      currentTimestamp = result.timestamp;

      // Mostrar estado inicial
      updateStatusPanel({
        estado: 'iniciado',
        parametros: result.parametros,
        timestamp: result.timestamp
      });

      // Polling de estado cada 3 segundos
      if (statusInterval) clearInterval(statusInterval);
      statusInterval = setInterval(() => {
        if (currentTimestamp && isSearching) checkStatus();
      }, 3000);

    } catch (err) {
      console.error("Error iniciando scraping:", err);
      showNotification(`Error: ${err.message}`, "danger");
      setSearchingState(false);
    } finally {
      hideLoader();
    }
  }

  async function checkStatus() {
    if (!currentTimestamp) return;

    try {
      const resp = await fetch(`/consejo_estado/status/${currentTimestamp}`);
      const data = await resp.json();

      if (!resp.ok) {
        throw new Error(data.message || `HTTP ${resp.status}`);
      }

      updateStatusPanel(data);

      // Si hay reporte final, detener polling
      if (data.final_report) {
        setSearchingState(false);
        clearInterval(statusInterval);
        showNotification("Búsqueda completada", "success");
      }
    } catch (err) {
      console.error("Error consultando estado:", err);
    }
  }

  function updateStatusPanel(data) {
    const statusContent = document.getElementById("status-content");
    let html = "";

    // Si hay reporte final, mostrar resumen estilo jurisprudencia/tesauro
    if (data.final_report) {
      const report = data.final_report;
      const resumen = report.resumen || {};

      html = `
        <!-- Estado del Proceso -->
        <div class="status-card">
          <div class="status-header">
            <span class="status-badge completado">
              <i class="fas fa-check-circle"></i>
              completado
            </span>
            <span class="status-date">${new Date(report.fecha_fin).toLocaleString('es-ES')}</span>
          </div>
          
          <div class="expected-total">
            <p>Total esperados:</p>
            <div class="number">${resumen.total_esperados || 0}</div>
          </div>
        </div>

        <!-- Panel de Búsqueda Completada -->
        <div class="completion-summary">
          <div class="summary-header">
            <i class="fas fa-check-circle"></i>
            <h4>Búsqueda Completada</h4>
          </div>
          
          <div class="main-stats">
            <div class="stat-item">
              <div class="stat-value">${resumen.total_esperados || 0}</div>
              <div class="stat-label">Documentos Esperados</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">${resumen.total_documentos || 0}</div>
              <div class="stat-label">Documentos Procesados</div>
            </div>
            <div class="stat-item">
              <div class="stat-value success">${resumen.pdfs_descargados || 0}</div>
              <div class="stat-label">ZIPs Descargados</div>
            </div>
            <div class="stat-item">
              <div class="stat-value error">${resumen.errores_descarga || 0}</div>
              <div class="stat-label">Errores</div>
            </div>
          </div>
          
          <div class="summary-details">
            <p><strong>Duración:</strong> <span>${report.duracion_formateada || '-'}</span></p>
            <p><strong>Tamaño total:</strong> <span>${resumen.tamaño_total_mb || 0} MB</span></p>
            <p><strong>Fecha:</strong> <span>${new Date(report.fecha_inicio).toLocaleString('es-ES')}</span></p>
          </div>
        </div>

        <!-- Reporte Final -->
        <div class="final-report-section">
          <div class="report-header">
            <i class="fas fa-chart-bar"></i>
            Reporte Final
          </div>
          
          <div class="report-stats">
            <div class="report-stat">
              <label>Recolectados:</label>
              <span class="value">${resumen.total_documentos || 0}</span>
            </div>
            <div class="report-stat">
              <label>Descargados:</label>
              <span class="value success">${resumen.pdfs_descargados || 0}</span>
            </div>
            <div class="report-stat">
              <label>Errores:</label>
              <span class="value error">${resumen.errores_descarga || 0}</span>
            </div>
            <div class="report-stat">
              <label>Tasa de éxito:</label>
              <span class="value success">${calcularTasaExito(resumen)}%</span>
            </div>
          </div>
        </div>
      `;

      // Mostrar botones de descarga
      document.getElementById("btn-download-csv").style.display = "inline-flex";
      document.getElementById("btn-download-manifest").style.display = "inline-flex";

    } else if (data.manifest) {
      // Estado en proceso
      const manifest = data.manifest;
      const procesados = manifest.total_procesados || 0;
      const esperados = manifest.total_esperados || 0;

      html = `
        <!-- Estado del Proceso -->
        <div class="status-card">
          <div class="status-header">
            <span class="status-badge iniciado">
              <i class="fas fa-clock"></i>
              iniciado
            </span>
            <span class="status-date">${new Date().toLocaleString('es-ES')}</span>
          </div>
          
          <div class="expected-total">
            <p>Total esperados:</p>
            <div class="number">${esperados}</div>
          </div>
        </div>
      `;
    } else if (data.estado === 'iniciado') {
      // Estado inicial
      html = `
        <!-- Estado del Proceso -->
        <div class="status-card">
          <div class="status-header">
            <span class="status-badge iniciado">
              <i class="fas fa-clock"></i>
              iniciado
            </span>
            <span class="status-date">${new Date().toLocaleString('es-ES')}</span>
          </div>
          
          <div class="expected-total">
            <p>Obteniendo total de documentos...</p>
          </div>
        </div>
      `;
    }

    statusContent.innerHTML = html;
  }

  function calcularTasaExito(resumen) {
    const total = resumen.total_documentos || 0;
    const exitosos = resumen.pdfs_descargados || 0;
    if (total === 0) return "0.00";
    return ((exitosos / total) * 100).toFixed(2);
  }

  function showLoader(text = "Procesando...") {
    document.getElementById("loader-text").textContent = text;
    document.getElementById("loader-overlay").style.display = "flex";
  }

  function hideLoader() {
    document.getElementById("loader-overlay").style.display = "none";
  }

  function cancelSearch() {
    if (!currentTimestamp) return;

    if (confirm("¿Estás seguro de que deseas cancelar la búsqueda en curso?")) {
      fetch(`/consejo_estado/cancel_scraping/${currentTimestamp}`, { method: "POST" })
        .then(res => res.json())
        .then(resp => {
          showNotification("Búsqueda cancelada", "warning");
          setSearchingState(false);
          clearInterval(statusInterval);
          checkStatus(); // Actualizar estado final
        })
        .catch(err => console.error("Error cancelando:", err));
    }
  }

  function newSearch() {
    window.location.reload();
  }

  function downloadManifest() {
    if (!currentTimestamp) return;
    const url = `/logs/consejo_estado/${currentTimestamp}/manifest.json`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `consejo_estado_manifest_${currentTimestamp}.json`;
    a.click();
  }

  function downloadCSV() {
    if (!currentTimestamp) return;
    window.location.href = `/consejo_estado/download_csv/${currentTimestamp}`;
  }

  function showNotification(msg, type = "info") {
    // Crear notificación tipo toast
    const notification = document.createElement("div");
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
      <i class="fas fa-${type === 'success' ? 'check' : type === 'warning' ? 'exclamation' : type === 'danger' ? 'times' : 'info'}-circle"></i>
      <span>${msg}</span>
    `;

    document.body.appendChild(notification);

    // Animar entrada
    setTimeout(() => notification.classList.add("show"), 10);

    // Remover después de 3 segundos
    setTimeout(() => {
      notification.classList.remove("show");
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }
});