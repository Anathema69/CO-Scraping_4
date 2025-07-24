# app.py - Con cancelación real de procesos
import threading
import webbrowser
import json
from flask import Flask, render_template, request, Response, jsonify

from datetime import datetime

# CAMBIOS: Solo estos 2 imports cambiaron
from scrapers.jurisprudencia_scraper import JudicialScraper
from utils.form_helpers import build_search_params

import logging

app = Flask(__name__)

# Configurar logging para la app
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# NUEVO: Diccionario global para controlar cancelaciones
cancel_events = {}
active_scrapers = {}


@app.route('/')
def dashboard():
    """Dashboard principal - página de inicio"""
    return render_template('index.html')


@app.route('/jurisprudencia')
def jurisprudencia_filters():
    """Página de filtros de jurisprudencia"""
    return render_template('jurisprudencia/filters.html')


@app.route('/search', methods=['POST'])
def search():
    """Endpoint que recibe los filtros y retorna el JSON de parámetros (para debugging)"""
    params = build_search_params(request.form)

    # Generar JSON mostrando el formato real
    json_output = json.dumps(params, indent=4, ensure_ascii=False)

    return Response(json_output, mimetype='application/json')


@app.route('/start_scraping', methods=['POST'])
def start_scraping():
    """Endpoint que inicia el proceso de scraping con los filtros del formulario"""
    try:
        # Obtener parámetros del formulario
        search_params = build_search_params(request.form)

        # Parámetros adicionales para el scraper
        download_pdfs = request.form.get('download_pdfs', 'true').lower() == 'true'
        max_results = request.form.get('max_results', None)
        max_workers = int(request.form.get('max_workers', '3'))

        if max_results:
            max_results = int(max_results)

        # Crear instancia del scraper
        scraper = JudicialScraper()
        timestamp = scraper.timestamp

        # NUEVO: Crear evento de cancelación
        cancel_event = threading.Event()
        cancel_events[timestamp] = cancel_event
        active_scrapers[timestamp] = scraper

        # Ejecutar scraping en un hilo separado para no bloquear la respuesta
        def run_scraper():
            try:
                logger.info("Iniciando proceso de scraping...")
                results = scraper.search_and_download_with_params(
                    search_params=search_params,
                    download_pdfs=download_pdfs,
                    max_results=max_results,
                    max_workers=max_workers,
                    cancel_event=cancel_event  # NUEVO: Pasar evento de cancelación
                )

                if results is None:
                    logger.info("Scraping cancelado por el usuario")
                else:
                    logger.info(f"Scraping completado. Resultados: {len(results) if results else 0}")

            except Exception as e:
                logger.error(f"Error en scraping: {str(e)}")
            finally:
                # NUEVO: Limpiar eventos al terminar
                if timestamp in cancel_events:
                    del cancel_events[timestamp]
                if timestamp in active_scrapers:
                    del active_scrapers[timestamp]

        # Iniciar en hilo separado
        thread = threading.Thread(target=run_scraper)
        thread.daemon = True
        thread.start()

        # Respuesta inmediata
        response_data = {
            'status': 'started',
            'message': 'Proceso de scraping iniciado correctamente',
            'timestamp': timestamp,
            'log_dir': str(scraper.log_dir),
            'pdf_dir': str(scraper.pdf_dir),
            'parametros': {
                'fechas': f"{search_params.get('searchForm:fechaIniCal')} - {search_params.get('searchForm:fechaFinCal')}",
                'download_pdfs': download_pdfs,
                'max_results': max_results,
                'max_workers': max_workers
            }
        }

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error iniciando scraping: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error al iniciar el proceso: {str(e)}'
        }), 500


# NUEVA RUTA: Cancelar scraping real
@app.route('/cancel_scraping/<timestamp>', methods=['POST'])
def cancel_scraping(timestamp):
    """Cancelar proceso de scraping activo"""
    try:
        if timestamp in cancel_events:
            # Activar evento de cancelación
            cancel_events[timestamp].set()

            # Actualizar manifiesto si existe
            if timestamp in active_scrapers:
                scraper = active_scrapers[timestamp]
                manifest_path = scraper.log_dir / 'manifest.json'

                if manifest_path.exists():
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)

                    manifest['estado'] = 'cancelado'
                    manifest['fecha_cancelacion'] = datetime.now().isoformat()

                    with open(manifest_path, 'w', encoding='utf-8') as f:
                        json.dump(manifest, f, ensure_ascii=False, indent=2)

            logger.info(f"Proceso {timestamp} cancelado por el usuario")

            return jsonify({
                'status': 'cancelled',
                'message': 'Proceso cancelado correctamente'
            })
        else:
            return jsonify({
                'status': 'not_found',
                'message': 'Proceso no encontrado o ya terminado'
            }), 404

    except Exception as e:
        logger.error(f"Error cancelando proceso {timestamp}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error al cancelar proceso: {str(e)}'
        }), 500


@app.route('/scraping_status/<timestamp>')
def scraping_status(timestamp):
    """Endpoint para consultar el estado de un proceso de scraping"""
    try:
        from pathlib import Path

        log_dir = Path(f"logs/{timestamp}")
        manifest_path = log_dir / 'manifest.json'

        if not manifest_path.exists():
            return jsonify({
                'status': 'not_found',
                'message': 'Proceso no encontrado'
            }), 404

        # Leer manifiesto
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        # Leer reporte final si existe
        report_path = log_dir / 'reporte_final.json'
        final_report = None
        if report_path.exists():
            with open(report_path, 'r', encoding='utf-8') as f:
                final_report = json.load(f)

        return jsonify({
            'status': 'success',
            'manifest': manifest,
            'final_report': final_report,
            'files': {
                'log_exists': (log_dir / 'descarga.log').exists(),
                'results_json_exists': (log_dir / 'resultados_completos.json').exists(),
                'results_csv_exists': list(log_dir.glob('jurisprudencia_*.csv')) != []
            }
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/download_csv/<timestamp>')
def download_csv(timestamp):
    """Descargar archivo CSV de resultados"""
    try:
        from pathlib import Path
        from flask import send_file

        # Buscar archivo CSV en el directorio de logs
        log_dir = Path(f"logs/{timestamp}")
        csv_files = list(log_dir.glob('jurisprudencia_*.csv'))

        if not csv_files:
            return "Archivo CSV no encontrado", 404

        # Tomar el primer archivo CSV encontrado
        csv_file = csv_files[0]

        if csv_file.exists():
            return send_file(
                csv_file,
                as_attachment=True,
                download_name=f'jurisprudencia_{timestamp}.csv',
                mimetype='text/csv'
            )
        else:
            return "Archivo CSV no encontrado", 404

    except Exception as e:
        logger.error(f"Error descargando CSV: {str(e)}")
        return f"Error al descargar archivo: {str(e)}", 500


@app.route('/logs/<timestamp>/<filename>')
def serve_logs(timestamp, filename):
    """Servir archivos de log"""
    try:
        from pathlib import Path

        log_file = Path(f"logs/{timestamp}/{filename}")
        if log_file.exists() and log_file.suffix == '.log':
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            return Response(content, mimetype='text/plain')
        else:
            return "Archivo no encontrado", 404

    except Exception as e:
        return f"Error: {str(e)}", 500


if __name__ == '__main__':
    # Auto-abre el navegador
    threading.Timer(1.0, lambda: webbrowser.open('http://127.0.0.1:5000/')).start()
    app.run(debug=True, use_reloader=False)