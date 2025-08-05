# app.py - Aplicación unificada para todos los scrapers
import threading
import webbrowser
import json
from flask import Flask, render_template, request, Response, jsonify, send_file
from datetime import datetime
from pathlib import Path
import logging

# Importar scrapers
from scrapers.jurisprudencia.scraper import JudicialScraperV2
from scrapers.tesauro.scraper import TesauroScraper
from utils.form_helpers import build_search_params

#Para la biblioteca nacional


from scrapers.biblioteca_ccb import BibliotecaCCBScraper
from scrapers.biblioteca_ccb.ccb_scraper_patched import CCBArbitrajeScraper
import os

# Variable global para el estado del scraper
biblioteca_ccb_status = {
    'in_progress': False,
    'scraper': None,
    'thread': None,
    'result': None
}

app = Flask(__name__)

# Configurar logging para la app
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Diccionarios globales para controlar procesos
cancel_events = {}
active_scrapers = {}


# =====================
# RUTAS PRINCIPALES
# =====================

@app.route('/')
def dashboard():
    """Dashboard principal - página de inicio"""
    return render_template('index.html')


# =====================
# RUTAS DE JURISPRUDENCIA
# =====================



@app.route('/jurisprudencia/search', methods=['POST'])
def jurisprudencia_search():
    """Endpoint que recibe los filtros y retorna el JSON de parámetros (para debugging)"""
    params = build_search_params(request.form)
    json_output = json.dumps(params, indent=4, ensure_ascii=False)
    return Response(json_output, mimetype='application/json')


@app.route('/jurisprudencia/start_scraping', methods=['POST'])
def jurisprudencia_start_scraping():
    """Endpoint que inicia el proceso de scraping de jurisprudencia"""
    try:
        # Obtener parámetros del formulario
        search_params = build_search_params(request.form)

        # Parámetros básicos para el scraper
        download_pdfs = request.form.get('download_pdfs', 'true').lower() == 'true'
        max_results = request.form.get('max_results', None)
        max_workers = int(request.form.get('max_workers', '3'))

        if max_results:
            max_results = int(max_results)

        # Crear instancia del scraper
        scraper = JudicialScraperV2()
        timestamp = scraper.timestamp

        # Crear evento de cancelación
        cancel_event = threading.Event()
        cancel_events[f'jurisprudencia_{timestamp}'] = cancel_event
        active_scrapers[f'jurisprudencia_{timestamp}'] = scraper

        # Ejecutar scraping en un hilo separado
        def run_scraper():
            try:
                logger.info("Iniciando proceso de scraping de jurisprudencia...")
                logger.info(
                    f"Período: {search_params.get('searchForm:fechaIniCal')} - {search_params.get('searchForm:fechaFinCal')}")
                logger.info(f"Descargar PDFs: {download_pdfs}")
                logger.info(f"Max resultados: {max_results}")
                logger.info(f"Workers: {max_workers}")

                results = scraper.search_and_download_with_params(
                    search_params=search_params,
                    download_pdfs=download_pdfs,
                    max_results=max_results,
                    max_workers=max_workers,
                    cancel_event=cancel_event
                )

                if results is None:
                    logger.info("Scraping de jurisprudencia cancelado por el usuario")
                else:
                    logger.info(f"Scraping de jurisprudencia completado. Resultados: {len(results) if results else 0}")

            except Exception as e:
                logger.error(f"Error en scraping de jurisprudencia: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                # Limpiar eventos al terminar
                if f'jurisprudencia_{timestamp}' in cancel_events:
                    del cancel_events[f'jurisprudencia_{timestamp}']
                if f'jurisprudencia_{timestamp}' in active_scrapers:
                    del active_scrapers[f'jurisprudencia_{timestamp}']

        # Iniciar en hilo separado
        thread = threading.Thread(target=run_scraper)
        thread.daemon = True
        thread.start()

        # Respuesta inmediata
        response_data = {
            'status': 'started',
            'message': 'Proceso de scraping de jurisprudencia iniciado correctamente',
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
        logger.error(f"Error iniciando scraping de jurisprudencia: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error al iniciar el proceso: {str(e)}'
        }), 500


@app.route('/jurisprudencia/cancel_scraping/<timestamp>', methods=['POST'])
def jurisprudencia_cancel_scraping(timestamp):
    """Cancelar proceso de scraping de jurisprudencia activo"""
    try:
        key = f'jurisprudencia_{timestamp}'
        if key in cancel_events:
            # Activar evento de cancelación
            cancel_events[key].set()

            # Actualizar manifiesto si existe
            if key in active_scrapers:
                scraper = active_scrapers[key]
                manifest_path = scraper.log_dir / 'manifest.json'

                if manifest_path.exists():
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)

                    manifest['estado'] = 'cancelado'
                    manifest['fecha_cancelacion'] = datetime.now().isoformat()

                    with open(manifest_path, 'w', encoding='utf-8') as f:
                        json.dump(manifest, f, ensure_ascii=False, indent=2)

            logger.info(f"Proceso de jurisprudencia {timestamp} cancelado por el usuario")

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
        logger.error(f"Error cancelando proceso de jurisprudencia {timestamp}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error al cancelar proceso: {str(e)}'
        }), 500


@app.route('/jurisprudencia/scraping_status/<timestamp>')
def jurisprudencia_scraping_status(timestamp):
    """Endpoint para consultar el estado de un proceso de scraping de jurisprudencia"""
    try:
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


@app.route('/jurisprudencia/download_csv/<timestamp>')
def jurisprudencia_download_csv(timestamp):
    """Descargar archivo CSV de resultados de jurisprudencia"""
    try:
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
        logger.error(f"Error descargando CSV de jurisprudencia: {str(e)}")
        return f"Error al descargar archivo: {str(e)}", 500


# =====================
# RUTAS DEL TESAURO
# =====================




@app.route('/tesauro/preview', methods=['POST'])
def tesauro_preview():
    """Obtener una vista previa de los resultados del tesauro (sin descargar PDFs)"""
    try:
        # Obtener filtros del formulario
        filters = {
            'tipo_contenido': request.form.get('tipo_contenido'),
            'fecha_desde': request.form.get('fecha_desde'),
            'fecha_hasta': request.form.get('fecha_hasta')
        }

        # Limpiar filtros vacíos
        filters = {k: v for k, v in filters.items() if v}

        # Crear scraper y buscar solo 5 resultados como preview
        scraper = TesauroScraper()
        results = scraper.search_documents(filters, max_results=5)

        return jsonify({
            'status': 'success',
            'total_found': len(results),
            'preview': results,
            'message': f'Se encontraron {len(results)} documentos (mostrando primeros 5)'
        })

    except Exception as e:
        logger.error(f"Error en preview del tesauro: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/tesauro/start_scraping', methods=['POST'])
def tesauro_start_scraping():
    """Endpoint que inicia el proceso de scraping del tesauro"""
    try:
        # Obtener filtros del formulario
        filters = {
            'tipo_contenido': request.form.get('tipo_contenido'),
            'fecha_desde': request.form.get('fecha_desde'),
            'fecha_hasta': request.form.get('fecha_hasta')
        }

        # Limpiar filtros vacíos
        filters = {k: v for k, v in filters.items() if v}

        # Manejar correctamente el checkbox
        download_pdfs = request.form.get('download_pdfs') == 'true'

        # Obtener otros parámetros
        max_results = request.form.get('max_results', '').strip()
        max_workers = request.form.get('max_workers', '3').strip()

        # Convertir max_results a int o None
        if max_results:
            max_results = int(max_results)
        else:
            max_results = None

        # Convertir max_workers a int
        max_workers = int(max_workers) if max_workers else 3

        # Crear instancia del scraper
        scraper = TesauroScraper()
        timestamp = scraper.timestamp

        # Crear evento de cancelación
        cancel_event = threading.Event()
        cancel_events[f'tesauro_{timestamp}'] = cancel_event
        active_scrapers[f'tesauro_{timestamp}'] = scraper

        # Ejecutar scraping en un hilo separado
        def run_scraper():
            try:
                logger.info("Iniciando scraping del tesauro...")
                logger.info(f"Filtros: {filters}")
                logger.info(f"Descargar PDFs: {download_pdfs}")
                logger.info(f"Max resultados: {max_results}")
                logger.info(f"Max workers: {max_workers}")

                results = scraper.search_and_download(
                    filters=filters,
                    download_pdfs=download_pdfs,
                    max_results=max_results,
                    max_workers=max_workers
                )

                logger.info(f"Scraping del tesauro completado. Resultados: {len(results) if results else 0}")

            except Exception as e:
                logger.error(f"Error en scraping del tesauro: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                # Limpiar eventos al terminar
                if f'tesauro_{timestamp}' in cancel_events:
                    del cancel_events[f'tesauro_{timestamp}']
                if f'tesauro_{timestamp}' in active_scrapers:
                    del active_scrapers[f'tesauro_{timestamp}']

        # Iniciar en hilo separado
        thread = threading.Thread(target=run_scraper)
        thread.daemon = True
        thread.start()

        # Respuesta inmediata
        response_data = {
            'status': 'started',
            'message': 'Proceso de scraping del tesauro iniciado correctamente',
            'timestamp': timestamp,
            'log_dir': str(scraper.log_dir),
            'pdf_dir': str(scraper.pdf_dir),
            'parametros': {
                'filtros': filters,
                'download_pdfs': download_pdfs,
                'max_results': max_results,
                'max_workers': max_workers
            }
        }

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error iniciando scraping del tesauro: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': f'Error al iniciar el proceso: {str(e)}'
        }), 500


@app.route('/tesauro/cancel_scraping/<timestamp>', methods=['POST'])
def tesauro_cancel_scraping(timestamp):
    """Cancelar proceso de scraping del tesauro activo"""
    try:
        key = f'tesauro_{timestamp}'
        if key in cancel_events:
            # Activar evento de cancelación
            cancel_events[key].set()

            logger.info(f"Proceso del tesauro {timestamp} cancelado por el usuario")

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
        logger.error(f"Error cancelando proceso del tesauro {timestamp}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error al cancelar proceso: {str(e)}'
        }), 500


@app.route('/tesauro/status/<timestamp>')
def tesauro_status(timestamp):
    """Endpoint para consultar el estado de un proceso de scraping del tesauro"""
    try:
        log_dir = Path(f"logs/tesauro_{timestamp}")

        if not log_dir.exists():
            return jsonify({
                'status': 'not_found',
                'message': 'Proceso no encontrado'
            }), 404

        # Buscar archivos generados
        files = {
            'log_exists': (log_dir / 'tesauro_scraping.log').exists(),
            'results_json_exists': list(log_dir.glob('tesauro_resultados_*.json')) != [],
            'results_csv_exists': list(log_dir.glob('tesauro_resultados_*.csv')) != [],
            'report_exists': (log_dir / 'reporte_final.json').exists()
        }

        # Leer reporte final si existe
        final_report = None
        report_path = log_dir / 'reporte_final.json'
        if report_path.exists():
            with open(report_path, 'r', encoding='utf-8') as f:
                final_report = json.load(f)

        # Leer últimas líneas del log
        log_tail = []
        log_path = log_dir / 'tesauro_scraping.log'
        if log_path.exists():
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                log_tail = lines[-20:]  # Últimas 20 líneas

        return jsonify({
            'status': 'success',
            'files': files,
            'final_report': final_report,
            'log_tail': log_tail
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# Agregar estas rutas al archivo app.py después de las rutas del tesauro

# =====================
# RUTAS DEL CONSEJO DE ESTADO
# =====================




@app.route('/consejo_estado/preview', methods=['POST'])
def consejo_estado_preview():
    """Obtener una vista previa de los resultados"""
    try:
        # Obtener filtros del formulario
        filters = {
            'sala_decision': request.form.get('sala_decision'),
            'fecha_desde': request.form.get('fecha_desde'),
            'fecha_hasta': request.form.get('fecha_hasta')
        }

        # Validar filtros
        if not all(filters.values()):
            return jsonify({
                'status': 'error',
                'message': 'Todos los filtros son requeridos'
            }), 400

        # Importar el scraper
        from scrapers.consejo_estado import ConsejoEstadoScraper

        # Crear scraper temporal para preview
        scraper = ConsejoEstadoScraper()

        # Hacer búsqueda limitada
        results = scraper.search_and_download(
            filters=filters,
            download_pdfs=False,  # No descargar en preview
            max_results=5  # Solo 5 resultados para preview
        )

        return jsonify({
            'status': 'success',
            'total_found': len(results),
            'preview': results,
            'message': f'Se encontraron documentos (mostrando primeros {len(results)})'
        })

    except Exception as e:
        logger.error(f"Error en preview del Consejo de Estado: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/consejo_estado/start_scraping', methods=['POST'])
def consejo_estado_start_scraping():
    """Iniciar proceso de scraping del Consejo de Estado"""
    try:
        # Obtener filtros del formulario
        filters = {
            'sala_decision': request.form.get('sala_decision'),
            'fecha_desde': request.form.get('fecha_desde'),
            'fecha_hasta': request.form.get('fecha_hasta')
        }

        # Validar filtros
        if not all(filters.values()):
            return jsonify({
                'status': 'error',
                'message': 'Todos los filtros son requeridos'
            }), 400

        # Obtener opciones
        download_pdfs = True
        max_results = request.form.get('max_results', '').strip()
        max_workers = 3

        # Convertir a int si es necesario
        max_results = int(max_results) if max_results else None
        max_workers = int(max_workers) if max_workers else 3

        # Log para debugging
        logger.info(f"Parámetros del Consejo de Estado:")
        logger.info(f"  - Filtros: {filters}")
        logger.info(f"  - download_pdfs: {download_pdfs}")
        logger.info(f"  - max_results: {max_results}")
        logger.info(f"  - max_workers: {max_workers}")

        # Importar el scraper
        from scrapers.consejo_estado import ConsejoEstadoScraper

        # Crear instancia del scraper
        scraper = ConsejoEstadoScraper()
        timestamp = scraper.timestamp

        # Crear evento de cancelación
        cancel_event = threading.Event()
        cancel_events[f'consejo_estado_{timestamp}'] = cancel_event
        active_scrapers[f'consejo_estado_{timestamp}'] = scraper

        # Ejecutar scraping en un hilo separado
        def run_scraper():
            try:
                logger.info("Iniciando scraping del Consejo de Estado...")

                results = scraper.search_and_download(
                    filters=filters,
                    download_pdfs=download_pdfs,
                    max_results=max_results,
                    max_workers=max_workers,
                    cancel_event=cancel_event
                )

                logger.info(f"Scraping del Consejo de Estado completado. "
                            f"Resultados: {len(results) if results else 0}")

            except Exception as e:
                logger.error(f"Error en scraping del Consejo de Estado: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                # Limpiar eventos al terminar
                if f'consejo_estado_{timestamp}' in cancel_events:
                    del cancel_events[f'consejo_estado_{timestamp}']
                if f'consejo_estado_{timestamp}' in active_scrapers:
                    del active_scrapers[f'consejo_estado_{timestamp}']

        # Iniciar en hilo separado
        thread = threading.Thread(target=run_scraper)
        thread.daemon = True
        thread.start()

        # Respuesta inmediata
        response_data = {
            'status': 'started',
            'message': 'Proceso de scraping del Consejo de Estado iniciado correctamente',
            'timestamp': timestamp,
            'log_dir': str(scraper.log_dir),
            'pdf_dir': str(scraper.pdf_dir),
            'parametros': {
                'filtros': filters,
                'download_pdfs': download_pdfs,
                'max_results': max_results,
                'max_workers': max_workers
            }
        }

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error iniciando scraping del Consejo de Estado: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': f'Error al iniciar el proceso: {str(e)}'
        }), 500


@app.route('/consejo_estado/cancel_scraping/<timestamp>', methods=['POST'])
def consejo_estado_cancel_scraping(timestamp):
    """Cancelar proceso de scraping activo"""
    try:
        key = f'consejo_estado_{timestamp}'
        if key in cancel_events:
            # Activar evento de cancelación
            cancel_events[key].set()

            logger.info(f"Proceso del Consejo de Estado {timestamp} cancelado por el usuario")

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
        logger.error(f"Error cancelando proceso del Consejo de Estado {timestamp}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error al cancelar proceso: {str(e)}'
        }), 500


@app.route('/consejo_estado/status/<timestamp>')
def consejo_estado_status(timestamp):
    """Consultar el estado de un proceso de scraping"""
    try:
        log_dir = Path(f"logs/consejo_estado_{timestamp}")

        if not log_dir.exists():
            return jsonify({
                'status': 'not_found',
                'message': 'Proceso no encontrado'
            }), 404

        # Buscar archivos generados
        files = {
            'log_exists': (log_dir / 'consejo_estado_scraping.log').exists(),
            'results_json_exists': (log_dir / 'resultados.json').exists(),
            'results_csv_exists': list(log_dir.glob('consejo_estado_*.csv')) != [],
            'manifest_exists': (log_dir / 'manifest.json').exists(),
            'report_exists': (log_dir / 'reporte_final.json').exists()
        }

        # Leer manifiesto si existe
        manifest = None
        manifest_path = log_dir / 'manifest.json'
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

        # Leer reporte final si existe
        final_report = None
        report_path = log_dir / 'reporte_final.json'
        if report_path.exists():
            with open(report_path, 'r', encoding='utf-8') as f:
                final_report = json.load(f)

        # Leer últimas líneas del log
        log_tail = []
        log_path = log_dir / 'consejo_estado_scraping.log'
        if log_path.exists():
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                log_tail = lines[-20:]  # Últimas 20 líneas

        return jsonify({
            'status': 'success',
            'files': files,
            'manifest': manifest,
            'final_report': final_report,
            'log_tail': log_tail
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/consejo_estado/download_csv/<timestamp>')
def consejo_estado_download_csv(timestamp):
    """Descargar archivo CSV de resultados"""
    try:
        from flask import send_file

        # Buscar archivo CSV en el directorio de logs
        log_dir = Path(f"logs/consejo_estado_{timestamp}")
        csv_files = list(log_dir.glob('consejo_estado_*.csv'))

        if not csv_files:
            return "Archivo CSV no encontrado", 404

        # Tomar el primer archivo CSV encontrado
        csv_file = csv_files[0]

        if csv_file.exists():
            return send_file(
                csv_file,
                as_attachment=True,
                download_name=f'consejo_estado_{timestamp}.csv',
                mimetype='text/csv'
            )
        else:
            return "Archivo CSV no encontrado", 404

    except Exception as e:
        logger.error(f"Error descargando CSV del Consejo de Estado: {str(e)}")
        return f"Error al descargar archivo: {str(e)}", 500


# Actualizar también la ruta de logs para soportar consejo_estado
# En la función serve_logs, agregar:
# elif system == 'consejo_estado':
#     log_file = Path(f"logs/consejo_estado_{timestamp}/{filename}")


@app.route('/tesauro/download_csv/<timestamp>')
def tesauro_download_csv(timestamp):
    """Descargar archivo CSV de resultados del tesauro"""
    try:
        # Buscar archivo CSV en el directorio de logs
        log_dir = Path(f"logs/tesauro_{timestamp}")
        csv_files = list(log_dir.glob('tesauro_resultados_*.csv'))

        if not csv_files:
            return "Archivo CSV no encontrado", 404

        # Tomar el primer archivo CSV encontrado
        csv_file = csv_files[0]

        if csv_file.exists():
            return send_file(
                csv_file,
                as_attachment=True,
                download_name=f'tesauro_{timestamp}.csv',
                mimetype='text/csv'
            )
        else:
            return "Archivo CSV no encontrado", 404

    except Exception as e:
        logger.error(f"Error descargando CSV del tesauro: {str(e)}")
        return f"Error al descargar archivo: {str(e)}", 500


# =====================
# RUTAS COMUNES
# =====================

@app.route('/logs/<system>/<timestamp>/<filename>')
def serve_logs(system, timestamp, filename):
    """Servir archivos de log de cualquier sistema"""
    try:
        if system == 'jurisprudencia':
            log_file = Path(f"logs/{timestamp}/{filename}")
        elif system == 'tesauro':
            log_file = Path(f"logs/tesauro_{timestamp}/{filename}")
        elif system == 'consejo_estado':
             log_file = Path(f"logs/consejo_estado_{timestamp}/{filename}")
        else:
            return "Sistema no válido", 400

        if log_file.exists() and log_file.suffix in ['.log', '.json', '.csv']:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            if filename.endswith('.json'):
                return Response(content, mimetype='application/json')
            elif filename.endswith('.csv'):
                return Response(content, mimetype='text/csv')
            else:
                return Response(content, mimetype='text/plain')
        else:
            return "Archivo no encontrado", 404

    except Exception as e:
        return f"Error: {str(e)}", 500


@app.route('/active_processes')
def active_processes():
    """Endpoint para obtener procesos activos"""
    processes = []

    for key, scraper in active_scrapers.items():
        process_type = 'jurisprudencia' if key.startswith('jurisprudencia_') else 'tesauro'
        timestamp = key.split('_', 1)[1]

        processes.append({
            'type': process_type,
            'timestamp': timestamp,
            'key': key,
            'active': key in cancel_events
        })

    return jsonify({
        'status': 'success',
        'processes': processes
    })


@app.route('/biblioteca_ccb')
def biblioteca_ccb():
    """Página principal de Biblioteca CCB"""
    return render_template('biblioteca_ccb/filters.html')


# Agregar estas rutas en app.py después de las rutas existentes de biblioteca_ccb

@app.route('/api/biblioteca_ccb/authors', methods=['GET'])
def biblioteca_ccb_get_authors():
    """Obtiene lista de autores disponibles"""
    try:
        letter = request.args.get('letter', None)

        # Crear instancia temporal del scraper
        from scrapers.biblioteca_ccb import BibliotecaCCBScraper
        scraper = BibliotecaCCBScraper()

        # Obtener lista de autores
        authors = scraper.get_authors_preview(letter)

        return jsonify({
            'status': 'success',
            'authors': authors,
            'total': len(authors)
        })

    except Exception as e:
        app.logger.error(f"Error obteniendo autores: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


# Modificar la ruta de búsqueda existente para soportar búsqueda por autor
# Reemplazar la función biblioteca_ccb_search completa en app.py con esta versión corregida:

@app.route('/api/biblioteca_ccb/search', methods=['POST'])
def biblioteca_ccb_search():
    """Inicia una búsqueda en la Biblioteca CCB"""
    global biblioteca_ccb_status

    try:
        # Log para debugging
        app.logger.info("Biblioteca CCB: Iniciando búsqueda")

        # Verificar si ya hay una búsqueda en progreso
        if biblioteca_ccb_status['in_progress']:
            return jsonify({
                'error': 'Ya hay una búsqueda en progreso',
                'status': 'busy'
            }), 400

        # Obtener datos del request
        data = request.get_json()
        if not data:
            return jsonify({
                'error': 'No se recibieron datos',
                'status': 'error'
            }), 400

        app.logger.info(f"Biblioteca CCB: Datos recibidos: {data}")

        # Obtener tipo de filtro y valores
        filtro = data.get('filtro', 'fecha')
        date_filter = None
        author_filter = None
        browse_type = 'dateissued'

        if filtro == 'fecha':
            date_filter = data.get('date_filter', None)
            browse_type = 'dateissued'
        elif filtro == 'autor':
            author_filter = data.get('autor', None)
            browse_type = 'author'
            if not author_filter:
                return jsonify({
                    'error': 'Se requiere el nombre del autor',
                    'status': 'error'
                }), 400

            # IMPORTANTE: Verificar si necesitamos resolver el nombre exacto del autor
            app.logger.info(f"Biblioteca CCB: Verificando autor: {author_filter}")

            # Crear una instancia temporal del scraper base para verificar el autor
            from scrapers.biblioteca_ccb.ccb_scraper_patched import CCBArbitrajeScraper
            temp_scraper = CCBArbitrajeScraper()

            # Primero intentar búsqueda directa
            exact_author = temp_scraper.get_exact_author_match(author_filter)

            if exact_author is None:
                # Múltiples coincidencias, buscar autores parciales
                app.logger.info(f"Biblioteca CCB: Buscando coincidencias parciales para: {author_filter}")
                matches = temp_scraper.search_authors_by_partial_name(author_filter)

                if not matches:
                    return jsonify({
                        'status': 'no_matches',
                        'error': f'No se encontraron autores para: {author_filter}'
                    }), 404
                elif len(matches) > 1:
                    # Múltiples coincidencias, el usuario debe elegir
                    app.logger.info(f"Biblioteca CCB: {len(matches)} coincidencias encontradas")
                    return jsonify({
                        'status': 'multiple_matches',
                        'matches': matches,
                        'query': author_filter
                    })
                else:
                    # Una sola coincidencia, usar ese autor
                    author_filter = matches[0]['nombre']
                    app.logger.info(f"Biblioteca CCB: Una coincidencia encontrada, usando: {author_filter}")
            else:
                # Usar el nombre exacto del autor
                author_filter = exact_author
                app.logger.info(f"Biblioteca CCB: Usando autor exacto: {author_filter}")
        else:
            return jsonify({
                'error': f'Tipo de filtro no soportado: {filtro}',
                'status': 'not_implemented'
            }), 501

        limit = data.get('limit', None)

        app.logger.info(f"Biblioteca CCB: Tipo: {browse_type}, Filtro: {date_filter or author_filter}, Límite: {limit}")

        # Crear directorio de salida
        output_dir = os.path.join('descargas_biblioteca')
        os.makedirs(output_dir, exist_ok=True)

        # Inicializar scraper
        scraper = BibliotecaCCBScraper(output_dir=output_dir)
        biblioteca_ccb_status['scraper'] = scraper
        biblioteca_ccb_status['in_progress'] = True
        biblioteca_ccb_status['result'] = None

        # Función para ejecutar en thread
        def run_scraper():
            try:
                app.logger.info("Biblioteca CCB: Ejecutando scraper en thread")
                result = scraper.run(
                    date_filter=date_filter,
                    author_filter=author_filter,
                    browse_type=browse_type,
                    limit=limit
                )
                biblioteca_ccb_status['result'] = result
                app.logger.info(f"Biblioteca CCB: Scraper completado: {result}")
            except Exception as e:
                app.logger.error(f"Biblioteca CCB: Error en scraper: {str(e)}")
                biblioteca_ccb_status['result'] = {
                    'status': 'error',
                    'error': str(e),
                    'stats': {
                        'expected': 0,
                        'processed': 0,
                        'downloaded': 0,
                        'failed': 0,
                        'success_rate': 0
                    }
                }
            finally:
                biblioteca_ccb_status['in_progress'] = False

        # Iniciar thread
        thread = threading.Thread(target=run_scraper)
        thread.daemon = True
        thread.start()
        biblioteca_ccb_status['thread'] = thread

        return jsonify({
            'status': 'started',
            'message': 'Búsqueda iniciada',
            'filtro': filtro,
            'valor': date_filter or author_filter
        })

    except Exception as e:
        app.logger.error(f"Biblioteca CCB: Error en endpoint: {str(e)}")
        biblioteca_ccb_status['in_progress'] = False
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500


@app.route('/api/biblioteca_ccb/progress')
def biblioteca_ccb_progress():
    """Obtiene el progreso de la búsqueda actual"""
    global biblioteca_ccb_status

    try:
        if not biblioteca_ccb_status['in_progress']:
            return jsonify({
                'in_progress': False,
                'status': 'idle'
            })

        scraper = biblioteca_ccb_status['scraper']
        if scraper:
            progress = scraper.get_progress()
            progress['in_progress'] = True
            return jsonify(progress)

        return jsonify({
            'in_progress': True,
            'status': 'starting',
            'expected': 0,
            'processed': 0,
            'downloaded': 0,
            'failed': 0
        })

    except Exception as e:
        app.logger.error(f"Biblioteca CCB Progress: Error: {str(e)}")
        return jsonify({
            'error': str(e),
            'in_progress': False
        }), 500


@app.route('/api/biblioteca_ccb/status')
def biblioteca_ccb_status_check():
    """Verifica el estado de la búsqueda"""
    global biblioteca_ccb_status

    try:
        if biblioteca_ccb_status['result']:
            # Devolver resultado
            result = biblioteca_ccb_status['result']
            return jsonify(result)

        if biblioteca_ccb_status['in_progress']:
            return jsonify({
                'status': 'in_progress'
            })

        return jsonify({
            'status': 'idle'
        })

    except Exception as e:
        app.logger.error(f"Biblioteca CCB Status: Error: {str(e)}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500


@app.route('/api/biblioteca_ccb/search_authors', methods=['POST'])
def biblioteca_ccb_search_authors():
    """Busca autores por nombre parcial"""
    try:
        data = request.get_json()
        partial_name = data.get('partial_name', '').strip()

        if not partial_name:
            return jsonify({
                'status': 'error',
                'error': 'Se requiere un nombre parcial'
            }), 400

        # Crear instancia temporal del scraper
        from scrapers.biblioteca_ccb.ccb_scraper_patched import CCBArbitrajeScraper
        scraper = CCBArbitrajeScraper()

        # Buscar autores
        authors = scraper.search_authors_by_partial_name(partial_name)

        return jsonify({
            'status': 'success',
            'authors': authors,
            'total': len(authors),
            'query': partial_name
        })

    except Exception as e:
        app.logger.error(f"Error buscando autores: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
@app.route('/api/biblioteca_ccb/stop', methods=['POST'])
def biblioteca_ccb_stop():
    """Detiene la búsqueda actual"""
    global biblioteca_ccb_status

    try:
        if not biblioteca_ccb_status['in_progress']:
            return jsonify({
                'status': 'not_running',
                'message': 'No hay búsqueda en progreso'
            })

        # Marcar como no en progreso
        biblioteca_ccb_status['in_progress'] = False

        return jsonify({
            'status': 'stopped',
            'message': 'Búsqueda detenida'
        })

    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500


@app.route('/api/biblioteca_ccb/stats')
def biblioteca_ccb_stats():
    """Obtiene estadísticas de los laudos descargados"""
    try:
        from scrapers.biblioteca_ccb.data_extractor import BibliotecaCCBDataExtractor

        output_dir = os.path.join('downloads', 'biblioteca_ccb', 'laudos_arbitraje')

        if not os.path.exists(output_dir):
            return jsonify({
                'stats': {
                    'total_laudos': 0,
                    'con_pdf': 0,
                    'sin_pdf': 0,
                    'por_año': {},
                    'por_materia': {},
                    'arbitros_frecuentes': []
                }
            })

        extractor = BibliotecaCCBDataExtractor(data_dir=output_dir)
        stats = extractor.get_statistics()
        return jsonify(stats)

    except Exception as e:
        app.logger.error(f"Biblioteca CCB Stats: Error: {str(e)}")
        return jsonify({
            'error': str(e),
            'stats': {}
        }), 500



@app.route('/jurisprudencia')
def jurisprudencia_filters():
    """Página de filtros de jurisprudencia"""
    return render_template('jurisprudencia/filters.html')

@app.route('/tesauro')
def tesauro_filters():
    """Página de filtros del tesauro"""
    return render_template('tesauro/filters.html')
@app.route('/consejo_estado')
def consejo_estado_filters():
    """Página de filtros del Consejo de Estado"""
    return render_template('consejo_estado/filters.html')

@app.route('/biblioteca_ccb')
def biblioteca_ccb_filters():
    return render_template('biblioteca_ccb/filters.html')

@app.route('/dian')
def dian_filters():
    return render_template('dian/filters.html')


if __name__ == '__main__':
    # Crear directorios necesarios
    Path('logs').mkdir(exist_ok=True)
    Path('descargas_pdf').mkdir(exist_ok=True)
    Path('descargas_tesauro').mkdir(exist_ok=True)
    Path('descargas_consejo_estado').mkdir(exist_ok=True)
    Path('templates/jurisprudencia').mkdir(parents=True, exist_ok=True)
    Path('templates/tesauro').mkdir(parents=True, exist_ok=True)
    Path('templates/consejo_estado').mkdir(parents=True, exist_ok=True)



    # Auto-abre el navegador
    threading.Timer(0.5, lambda: webbrowser.open('http://127.0.0.1:5000/')).start()

    # Ejecutar aplicación
    app.run(debug=True, port=5000, use_reloader=False)