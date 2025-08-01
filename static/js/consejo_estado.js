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
      alert("Completa sala de decisión y rango de fechas.");
      return;
    }

    setSearchingState(true);
    showLoader("Iniciando scraping del Consejo de Estado...");
    document.getElementById("results-panel").style.display = "block";

    const formData = new FormData();
    formData.append("sala_decision", sala);
    formData.append("fecha_desde", desde);
    formData.append("fecha_hasta", hasta);
    // campos ocultos que están en el HTML
    formData.append("max_workers", document.getElementById("max-workers").value || "3");

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
      updateStatusPanel({ manifest: result }); // inicializar con lo que venga

      // Polling de estado cada 5s
      if (statusInterval) clearInterval(statusInterval);
      statusInterval = setInterval(() => {
        if (currentTimestamp && isSearching) checkStatus();
      }, 5000);

    } catch (err) {
      console.error("Error iniciando scraping:", err);
      const statusContent = document.getElementById("status-content");
      statusContent.innerHTML = `<div class="alert alert-danger">Error: ${err.message}</div>`;
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

      // Si ya hay reporte final, detener polling
      if (data.final_report) {
        setSearchingState(false);
        clearInterval(statusInterval);
      }
    } catch (err) {
      console.error("Error consultando estado:", err);
    }
  }

  function updateStatusPanel(data) {
    const statusContent = document.getElementById("status-content");
    statusContent.innerHTML = "";

    // Mostrar manifest parcial o completo
    const manifest = data.manifest || data; // en el start_scraping la respuesta viene con timestamp etc.
    const finalReport = data.final_report;

    let html = "";

    if (finalReport) {
      html += `
        <div style="margin-bottom:1rem;">
          <h4>Scraping completado</h4>
          <div><strong>Total documentos:</strong> ${finalReport.resumen?.total_documentos || "-"}</div>
          <div><strong>ZIPs descargados:</strong> ${finalReport.resumen?.pdfs_descargados || "-"}</div>
          <div><strong>Errores:</strong> ${finalReport.resumen?.errores_descarga || "-"}</div>
          <div><strong>Duración:</strong> ${finalReport.duracion_segundos?.toFixed(2) || "-"}s</div>
        </div>
      `;
    }

    if (manifest && Array.isArray(manifest)) {
      // Si el manifest es la lista de resultados (caso directo)
      html += `<table class="table"><thead>
        <tr>
          <th>Radicado</th><th>Sala</th><th>Fecha providencia</th><th>Estado</th><th>Worker</th><th>Error</th>
        </tr></thead><tbody>`;
      manifest.forEach(item => {
        html += `
          <tr>
            <td>${item.numero_proceso || item.interno || "-"}</td>
            <td>${item.sala_decision || "-"}</td>
            <td>${item.fecha_providencia || item.fecha_proceso || "-"}</td>
            <td>${item.estado_descarga || "null"}</td>
            <td>${item.worker || "-"}</td>
            <td>${item.error || ""}</td>
          </tr>
        `;
      });
      html += `</tbody></table>`;
    } else if (manifest && manifest.timestamp) {
      // Estado inicial
      html += `
        <div>
          <div><strong>Timestamp:</strong> ${manifest.timestamp}</div>
          <div><strong>Filtros:</strong> ${JSON.stringify(manifest.parametros?.filtros || manifest.parametros || {})}</div>
          <div><strong>Workers:</strong> ${manifest.parametros?.max_workers || "-"}</div>
        </div>
      `;
    }

    statusContent.innerHTML = html;

    // Mostrar botón de descargar manifiesto
    document.getElementById("btn-download-manifest").style.display = "inline-flex";
  }

  function showLoader(text = "Procesando...") {
    document.getElementById("loader-text").textContent = text;
    document.getElementById("loader-overlay").style.display = "flex";
  }

  function hideLoader() {
    document.getElementById("loader-overlay").style.display = "none";
  }

  function cancelSearch() {
    // Lógica de cancelación similar a los otros scrapers si implementaste endpoint
    if (!currentTimestamp) return;
    fetch(`/consejo_estado/cancel_scraping/${currentTimestamp}`, { method: "POST" })
      .then(res => res.json())
      .then(resp => {
        showNotification("Cancelado: " + (resp.message || ""), "warning");
        setSearchingState(false);
        clearInterval(statusInterval);
      })
      .catch(err => console.error("Error cancelando:", err));
  }

  function newSearch() {
    window.location.reload();
  }

  function downloadManifest() {
    if (!currentTimestamp) return;
    // Se puede descargar desde el manifiesto en el servidor o reconstruir
    const url = `/logs/consejo_estado/${currentTimestamp}/manifest.json`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `consejo_estado_manifest_${currentTimestamp}.json`;
    a.click();
  }

  function showNotification(msg, type = "info") {
    // simple toast
    alert(msg);
  }
});
