// static/js/dian.js
document.addEventListener('DOMContentLoaded', () => {
  // --- Configuración de selectores ---
  const YEAR_START   = 2006;
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
  const yearSel       = document.getElementById('year');
  const monthSel      = document.getElementById('month');
  const searchBtn     = document.getElementById('searchButton');
  const resetBtn      = document.querySelector('.btn-secondary[onclick="resetForm()"]');
  const previewDiv    = document.getElementById('selectionPreview');
  const previewText   = document.getElementById('previewText');
  const loaderOverlay = document.getElementById('loader-overlay');
  const resultsPanel  = document.getElementById('results-panel');
  const statusContent = document.getElementById('status-content');
  const downloadBtn   = document.getElementById('btn-download-manifest');

  let dianTimestamp, dianInterval;

  // 1) Poblado de años
  for (let y = CURRENT_YEAR; y >= YEAR_START; y--) {
    const opt = document.createElement('option');
    opt.value = y;
    opt.textContent = y;
    yearSel.appendChild(opt);
  }

  // 2) Al cambiar año, habilitar/poblar mes
  yearSel.addEventListener('change', () => {
    monthSel.innerHTML = '<option value="">-- Mes (opcional) --</option>';
    monthSel.disabled = !yearSel.value;
    if (yearSel.value) {
      const maxM = yearSel.value == CURRENT_YEAR
                 ? new Date().getMonth() + 1
                 : 12;
      MONTHS.forEach(m => {
        if (parseInt(m.value) <= maxM) {
          const o = document.createElement('option');
          o.value = m.value;
          o.textContent = m.name;
          monthSel.appendChild(o);
        }
      });
    }
    updatePreview();
  });

  // 3) Al cambiar mes, actualizar preview
  monthSel.addEventListener('change', updatePreview);

  // 4) Reset del formulario
  resetBtn.addEventListener('click', () => {
    document.getElementById('searchForm').reset();
    monthSel.innerHTML = '<option value="">-- Primero seleccione un año --</option>';
    monthSel.disabled = true;
    previewDiv.style.display = 'none';
    searchBtn.disabled = true;
  });

  // 5) Función para habilitar botón y mostrar texto
  function updatePreview() {
    if (!yearSel.value) {
      previewDiv.style.display = 'none';
      searchBtn.disabled = true;
      return;
    }
    const txt = monthSel.value
      ? `${MONTHS.find(x => x.value === monthSel.value).name} de ${yearSel.value}`
      : `Todos los meses de ${yearSel.value}`;
    previewText.textContent = txt;
    previewDiv.style.display = 'flex';
    searchBtn.disabled = false;
  }

  // 6) Al clic en buscar, lanza scraper
  searchBtn.addEventListener('click', () => {
    if (!yearSel.value) return alert('Seleccione un año');
    const fd = new FormData();
    fd.append('year', yearSel.value);
    if (monthSel.value) fd.append('month', monthSel.value);

    loaderOverlay.style.display = 'flex';
    fetch('/dian/start_scraping', { method: 'POST', body: fd })
      .then(r => r.json())
      .then(data => {
        loaderOverlay.style.display = 'none';
        if (data.status === 'started') {
          dianTimestamp = data.timestamp;
          resultsPanel.style.display = 'block';
          statusContent.textContent = 'En progreso...';
          downloadBtn.style.display = 'none';
          dianInterval = setInterval(checkStatus, 5000);
        } else {
          alert(data.message || 'Error al iniciar scraping');
        }
      })
      .catch(_ => {
        loaderOverlay.style.display = 'none';

      });
  });

  // 7) Polling de estado
  function checkStatus() {
    fetch(`/dian/status/${dianTimestamp}`)
      .then(r => r.json())
      .then(data => {
        if (data.status === 'in_progress') {
          statusContent.textContent = 'En progreso...';
        } else {
          clearInterval(dianInterval);
          if (data.status === 'completed') {
            statusContent.textContent = `Completado. Total: ${data.result.total_documents}`;
            downloadBtn.style.display = 'inline-block';
          } else {
            statusContent.textContent = `Error: ${data.result.error||data.status}`;
          }
        }
      });
  }
});
