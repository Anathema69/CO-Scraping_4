# scrapers/jurisprudencia_scraper.py - Movido de scraping.py sin cambios
import requests
from urllib.parse import unquote
import re
from datetime import datetime
import time
import csv
import json
import os
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configuración
BASE_URL = "https://consultajurisprudencial.ramajudicial.gov.co"
INDEX_URL = f"{BASE_URL}/WebRelatoria/csj/index.xhtml"
PDF_URL = f"{BASE_URL}/WebRelatoria/FileReferenceServlet"

# Headers comunes
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
}


class JudicialScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = Path(f"logs/{self.timestamp}")
        self.pdf_dir = Path("descargas_pdf")
        self.setup_directories()
        self.setup_logging()
        self.download_queue = []
        self.results_lock = threading.Lock()

    def setup_directories(self):
        """Crear directorios necesarios"""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(exist_ok=True)

    def setup_logging(self):
        """Configurar sistema de logging"""
        log_file = self.log_dir / "descarga.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def extract_viewstate(self, html_content):
        """Extrae el ViewState del HTML"""
        pattern = r'<input type="hidden" name="javax\.faces\.ViewState".*?value="([^"]+)"'
        match = re.search(pattern, html_content)
        if match:
            return match.group(1)
        return None

    def clean_tema(self, tema_text, max_length=200):
        """Limpia y trunca el texto del tema"""
        if not tema_text:
            return ""

        # Limpiar HTML
        tema = tema_text.replace('<br>', ' ').replace('<b>', '').replace('</b>', '')
        tema = re.sub(r'<[^>]+>', '', tema).strip()

        # Opción 1: Cortar en el primer guión o salto de línea
        for delimiter in [' - ', '\n', '<br>']:
            if delimiter in tema:
                tema = tema.split(delimiter)[0].strip()
                break

        # Opción 2: Si aún es muy largo, truncar
        if len(tema) > max_length:
            tema = tema[:max_length] + "..."

        return tema

    def extract_jurisprudence_data(self, html_content):
        """Extrae TODOS los datos de jurisprudencia del HTML"""
        data = []

        # Extraer contenido CDATA
        cdata_pattern = r'<!\[CDATA\[(.*?)\]\]>'
        cdata_matches = re.findall(cdata_pattern, html_content, re.DOTALL)

        for cdata in cdata_matches:
            if 'ID:' in cdata and 'PROCESO:' in cdata:
                # Extraer todos los campos disponibles
                record = {}

                # ID
                id_match = re.search(r'ID:\s*</b></font><font[^>]*>(\d+)', cdata)
                record['id'] = id_match.group(1) if id_match else ''

                # Número de proceso
                proceso_match = re.search(r'PROCESO:\s*</b></font><font[^>]*>([^<]+)', cdata)
                record['numero_proceso'] = proceso_match.group(1) if proceso_match else ''

                # Número de providencia
                providencia_match = re.search(r'PROVIDENCIA:\s*</b></font><font[^>]*>([^<]+)', cdata)
                record['numero_providencia'] = providencia_match.group(1) if providencia_match else ''

                # Clase de actuación
                actuacion_match = re.search(r'ACTUACI[ÓO]N:\s*</b></font><font[^>]*>([^<]+)', cdata)
                record['clase_actuacion'] = actuacion_match.group(1) if actuacion_match else ''

                # Tipo de providencia
                tipo_match = re.search(r'TIPO DE PROVIDENCIA:\s*</b></font><font[^>]*>([^<]+)', cdata)
                record['tipo_providencia'] = tipo_match.group(1) if tipo_match else ''

                # Fecha
                fecha_match = re.search(r'FECHA:\s*</b></font><font[^>]*>([^<]+)', cdata)
                record['fecha'] = fecha_match.group(1) if fecha_match else ''

                # Ponente
                ponente_match = re.search(r'PONENTE:\s*</b></font><font[^>]*>([^<]+)', cdata)
                record['ponente'] = ponente_match.group(1) if ponente_match else ''

                # Tema (aplicar limpieza)
                tema_match = re.search(r'TEMA:\s*</b></font><font[^>]*>(.*?)</font>', cdata, re.DOTALL)
                if tema_match:
                    record['tema'] = self.clean_tema(tema_match.group(1))
                else:
                    record['tema'] = ''

                # Fuente formal (si existe)
                fuente_match = re.search(r'FUENTE FORMAL:\s*</b></font><font[^>]*>(.*?)</font>', cdata, re.DOTALL)
                if fuente_match:
                    fuente = fuente_match.group(1).replace('<br>', ' ')
                    fuente = re.sub(r'<[^>]+>', '', fuente).strip()
                    record['fuente_formal'] = fuente[:500] if len(fuente) > 500 else fuente
                else:
                    record['fuente_formal'] = ''

                # Agregar campos adicionales para el seguimiento
                record['nombre_archivo'] = None
                record['estado_descarga'] = 'pendiente'
                record['intentos'] = 0
                record['error'] = None
                record['tamaño_archivo'] = None
                record['fecha_descarga'] = None

                if record['id']:  # Solo agregar si tiene ID
                    data.append(record)

        return data

    def get_filename_from_cd(self, disposition, doc_id):
        """Extrae nombre de archivo de la cabecera Content-Disposition"""
        if not disposition:
            return f"{doc_id}.pdf"

        # Intentar diferentes patrones
        patterns = [
            r"filename\*=UTF-8''(?P<fname>[^;]+)",
            r'filename="(?P<fname>[^"]+)"',
            r'filename=([^;]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, disposition)
            if match:
                if 'fname' in match.groupdict():
                    return unquote(match.group('fname'))
                else:
                    return match.group(1).strip()

        return f"{doc_id}.pdf"

    def download_pdf_worker(self, record):
        """Worker para descargar un PDF (usado en threads)"""
        doc_id = record['id']
        pdf_params = {
            'corp': 'csj',
            'ext': 'pdf',
            'file': doc_id
        }

        # Crear una nueva sesión para cada thread
        session = requests.Session()
        session.headers.update(HEADERS)

        try:
            response = session.get(PDF_URL, params=pdf_params, timeout=30)

            if response.status_code == 200:
                # Obtener nombre del archivo
                content_disposition = response.headers.get('Content-Disposition')
                filename = self.get_filename_from_cd(content_disposition, doc_id)

                # Obtener contenido completo
                content = response.content

                # Verificar que es un PDF válido
                if len(content) < 1000 or not content.startswith(b'%PDF'):
                    raise Exception("El archivo no parece ser un PDF válido")

                # Guardar archivo
                filepath = self.pdf_dir / filename
                with open(filepath, 'wb') as f:
                    f.write(content)

                # Actualizar registro con thread safety
                with self.results_lock:
                    record['nombre_archivo'] = filename
                    record['estado_descarga'] = 'completado'
                    record['tamaño_archivo'] = len(content)
                    record['fecha_descarga'] = datetime.now().isoformat()

                self.logger.info(f"Descargado: {filename} ({len(content)} bytes)")
                return True, f"Descargado: {filename}"
            else:
                error_msg = f"Error HTTP {response.status_code}"
                with self.results_lock:
                    record['error'] = error_msg
                    record['estado_descarga'] = 'error'
                return False, error_msg

        except Exception as e:
            error_msg = str(e)
            with self.results_lock:
                record['error'] = error_msg
                record['estado_descarga'] = 'error'
            self.logger.error(f"Error descargando {doc_id}: {error_msg}")
            return False, error_msg
        finally:
            session.close()

    def save_manifest(self, search_params, total_results):
        """Guarda el manifiesto inicial"""
        manifest = {
            'timestamp': self.timestamp,
            'fecha_busqueda': datetime.now().isoformat(),
            'parametros_busqueda': search_params,
            'total_resultados_esperados': total_results,
            'estado': 'iniciado',
            'archivos_generados': {
                'log': str(self.log_dir / 'descarga.log'),
                'resultados_json': str(self.log_dir / 'resultados_completos.json'),
                'resultados_csv': str(self.log_dir / f'jurisprudencia_{self.timestamp}.csv'),
                'carpeta_pdfs': str(self.pdf_dir)
            }
        }

        manifest_path = self.log_dir / 'manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Manifiesto guardado en: {manifest_path}")
        return manifest

    def save_results(self, results):
        """Guarda los resultados en JSON y CSV"""
        # Guardar JSON completo
        json_path = self.log_dir / 'resultados_completos.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # Guardar CSV
        if results:
            csv_path = self.log_dir / f'jurisprudencia_{self.timestamp}.csv'
            # Seleccionar campos para CSV
            csv_fields = ['id', 'numero_providencia', 'numero_proceso', 'fecha',
                          'ponente', 'tipo_providencia', 'clase_actuacion',
                          'tema', 'nombre_archivo', 'estado_descarga']

            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(results)

        self.logger.info(f"Resultados guardados: {len(results)} registros")

    def generate_final_report(self, results, manifest):
        """Genera reporte final"""
        total_esperados = manifest['total_resultados_esperados']
        total_recolectados = len(results)
        total_descargados = sum(1 for r in results if r['estado_descarga'] == 'completado')
        total_errores = sum(1 for r in results if r['estado_descarga'] == 'error')
        total_pendientes = sum(1 for r in results if r['estado_descarga'] == 'pendiente')

        report = {
            'resumen': {
                'total_esperados': total_esperados,
                'total_recolectados': total_recolectados,
                'total_descargados': total_descargados,
                'total_errores': total_errores,
                'total_pendientes': total_pendientes,
                'tasa_exito': f"{(total_descargados / total_recolectados * 100):.2f}%" if total_recolectados > 0 else "0%"
            },
            'registros_con_error': [
                {
                    'id': r['id'],
                    'numero_providencia': r['numero_providencia'],
                    'error': r['error']
                }
                for r in results if r['estado_descarga'] == 'error'
            ],
            'tiempo_ejecucion': {
                'inicio': manifest['fecha_busqueda'],
                'fin': datetime.now().isoformat()
            }
        }

        report_path = self.log_dir / 'reporte_final.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Mostrar resumen en consola
        print("\n" + "=" * 50)
        print("REPORTE FINAL")
        print("=" * 50)
        print(f"Total esperados:    {total_esperados}")
        print(f"Total recolectados: {total_recolectados}")
        print(f"Total descargados:  {total_descargados}")
        print(f"Total con errores:  {total_errores}")
        print(f"Total pendientes:   {total_pendientes}")
        print(f"Tasa de éxito:      {report['resumen']['tasa_exito']}")
        print("=" * 50)

        return report

    def process_page_and_download(self, page_content, executor, futures):
        """Procesa una página y programa las descargas"""
        page_data = self.extract_jurisprudence_data(page_content)

        for record in page_data:
            # Programar descarga inmediata
            future = executor.submit(self.download_pdf_worker, record)
            futures[future] = record['id']

        return page_data

    def format_search_params(self, search_params, viewstate):
        """Formatea los parámetros de búsqueda con el ViewState real"""
        formatted_params = search_params.copy()

        # Actualizar ViewState real
        formatted_params['javax.faces.ViewState'] = viewstate

        # Formatear campos especiales que necesitan comillas
        if 'searchForm:tipoInput' in formatted_params and formatted_params['searchForm:tipoInput']:
            tipo_value = formatted_params['searchForm:tipoInput']
            formatted_params['searchForm:tipoInput'] = f'"{tipo_value}" '

        if 'searchForm:temaInput' in formatted_params and formatted_params['searchForm:temaInput']:
            tema_value = formatted_params['searchForm:temaInput']
            formatted_params['searchForm:temaInput'] = f'"{tema_value}" '

        return formatted_params

    def search_and_download_with_params(self, search_params, download_pdfs=True,
                                        max_results=None, max_workers=3):
        """Función que recibe parámetros externos del formulario web"""

        # Extraer fechas de los parámetros para logging
        fecha_inicio = search_params.get('searchForm:fechaIniCal', 'N/A')
        fecha_fin = search_params.get('searchForm:fechaFinCal', 'N/A')

        self.logger.info("=" * 50)
        self.logger.info("Iniciando scraper judicial con parámetros del formulario")
        self.logger.info(f"Período: {fecha_inicio} - {fecha_fin}")
        self.logger.info(f"Workers paralelos: {max_workers}")
        self.logger.info(f"Descargar PDFs: {download_pdfs}")
        self.logger.info("=" * 50)

        # Fase 1: Obtener página inicial
        self.logger.info("Fase 1: Obteniendo página inicial...")
        response = self.session.get(INDEX_URL)
        if response.status_code != 200:
            self.logger.error(f"Error en GET inicial: {response.status_code}")
            return None

        viewstate = self.extract_viewstate(response.text)
        if not viewstate:
            self.logger.error("No se pudo extraer ViewState")
            return None

        # Headers AJAX
        ajax_headers = {
            **HEADERS,
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Faces-Request': 'partial/ajax',
            'Accept': 'application/xml, text/xml, */*; q=0.01',
            'Origin': BASE_URL,
            'Referer': INDEX_URL,
        }

        # Fase 2: Preparar parámetros de búsqueda
        self.logger.info("Fase 2: Preparando parámetros de búsqueda...")

        # Actualizar ViewState real en los parámetros recibidos
        formatted_params = search_params.copy()
        formatted_params['javax.faces.ViewState'] = viewstate

        # CRÍTICO: Formatear campos especiales - FORMATO CORRECTO
        if 'searchForm:tipoInput' in formatted_params and formatted_params['searchForm:tipoInput']:
            tipo_value = formatted_params['searchForm:tipoInput']
            # FORMATO CORRECTO: '"VALOR"' (comillas dobles dentro de comillas simples)
            formatted_params['searchForm:tipoInput'] = f'"{tipo_value}"'

        if 'searchForm:temaInput' in formatted_params and formatted_params['searchForm:temaInput']:
            tema_value = formatted_params['searchForm:temaInput']
            # Mismo formato que tipo
            formatted_params['searchForm:temaInput'] = f'"{tema_value}"'

        # Debug: imprimir parámetros clave
        self.logger.info(f"Tipo providencia RAW: {repr(formatted_params.get('searchForm:tipoInput', 'N/A'))}")
        self.logger.info(f"Tema RAW: {repr(formatted_params.get('searchForm:temaInput', 'N/A'))}")
        self.logger.info(
            f"Fechas: {formatted_params.get('searchForm:fechaIniCal')} - {formatted_params.get('searchForm:fechaFinCal')}")
        self.logger.info(f"Asunto: {formatted_params.get('searchForm:tutelaselect', 'N/A')}")
        self.logger.info(f"Publicación: {formatted_params.get('searchForm:relevanteselect', 'N/A')}")
        self.logger.info(
            f"Salas seleccionadas: {len(formatted_params.get('searchForm:scivil', []) + formatted_params.get('searchForm:slaboral', []) + formatted_params.get('searchForm:spenal', []) + formatted_params.get('searchForm:splena', []))}")

        # Realizar búsqueda con parámetros del formulario
        self.logger.info("Realizando búsqueda...")
        response = self.session.post(INDEX_URL, data=formatted_params, headers=ajax_headers)

        if response.status_code != 200:
            self.logger.error(f"Error en búsqueda: {response.status_code}")
            return None

        # Obtener total de resultados
        results_pattern = r'Resultado:\s*(\d+)\s*/\s*(\d+)'
        match = re.search(results_pattern, response.text)
        if not match:
            self.logger.error("No se pudo determinar el número de resultados")
            return None

        total_results = int(match.group(2))
        if max_results and max_results < total_results:
            total_results = max_results
            self.logger.info(f"Limitando a {max_results} resultados")

        self.logger.info(f"Se encontraron {total_results} resultados")

        # Guardar manifiesto con parámetros completos
        manifest = self.save_manifest(formatted_params, total_results)

        # Fase 3: Recolectar metadatos y descargar (usar la lógica existente)
        self.logger.info("Fase 3: Recolectando metadatos y descargando PDFs...")
        all_results = []

        if download_pdfs:
            # Usar ThreadPoolExecutor para descargas paralelas
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}

                # Procesar primera página
                page_data = self.process_page_and_download(response.text, executor, futures)
                all_results.extend(page_data)

                # Navegar por páginas restantes (si hay más de 1 resultado)
                if total_results > 1:
                    nav_buttons = {'next': 'resultForm:j_idt258'}

                    for page in range(2, total_results + 1):
                        self.logger.info(f"Procesando página {page}/{total_results}...")

                        nav_params = {
                            'javax.faces.partial.ajax': 'true',
                            'javax.faces.source': nav_buttons['next'],
                            'javax.faces.partial.execute': '@all',
                            'javax.faces.partial.render': 'resultForm:jurisTable resultForm:pagText2',
                            nav_buttons['next']: nav_buttons['next'],
                            'resultForm': 'resultForm',
                            'resultForm:jurisTable_selection': '',
                            'javax.faces.ViewState': viewstate
                        }

                        try:
                            response = self.session.post(INDEX_URL, data=nav_params, headers=ajax_headers, timeout=30)
                            if response.status_code == 200:
                                page_data = self.process_page_and_download(response.text, executor, futures)
                                all_results.extend(page_data)
                            else:
                                self.logger.error(f"Error en página {page}: HTTP {response.status_code}")
                        except Exception as e:
                            self.logger.error(f"Error en página {page}: {str(e)}")

                        # Guardar progreso cada 10 páginas
                        if page % 10 == 0:
                            self.save_results(all_results)

                        time.sleep(0.5)  # Pausa entre navegación

                # Esperar a que terminen todas las descargas
                self.logger.info("Esperando a que terminen las descargas...")
                completed = 0
                for future in as_completed(futures):
                    completed += 1
                    doc_id = futures[future]
                    try:
                        success, msg = future.result()
                        if not success:
                            self.logger.warning(f"Descarga fallida para {doc_id}: {msg}")
                    except Exception as e:
                        self.logger.error(f"Excepción en descarga {doc_id}: {str(e)}")

                    if completed % 10 == 0:
                        self.logger.info(f"Progreso de descargas: {completed}/{len(futures)}")
        else:
            # Solo recolectar metadatos sin descargar
            page_data = self.extract_jurisprudence_data(response.text)
            all_results.extend(page_data)

            if total_results > 1:
                nav_buttons = {'next': 'resultForm:j_idt258'}

                for page in range(2, total_results + 1):
                    self.logger.info(f"Procesando página {page}/{total_results}...")

                    nav_params = {
                        'javax.faces.partial.ajax': 'true',
                        'javax.faces.source': nav_buttons['next'],
                        'javax.faces.partial.execute': '@all',
                        'javax.faces.partial.render': 'resultForm:jurisTable resultForm:pagText2',
                        nav_buttons['next']: nav_buttons['next'],
                        'resultForm': 'resultForm',
                        'resultForm:jurisTable_selection': '',
                        'javax.faces.ViewState': viewstate
                    }

                    try:
                        response = self.session.post(INDEX_URL, data=nav_params, headers=ajax_headers, timeout=30)
                        if response.status_code == 200:
                            page_data = self.extract_jurisprudence_data(response.text)
                            all_results.extend(page_data)
                    except Exception as e:
                        self.logger.error(f"Error en página {page}: {str(e)}")

                    time.sleep(0.5)

        # Guardar resultados finales
        self.save_results(all_results)

        # Generar reporte final
        report = self.generate_final_report(all_results, manifest)

        # Actualizar manifiesto
        manifest['estado'] = 'completado'
        manifest['fecha_fin'] = datetime.now().isoformat()
        with open(self.log_dir / 'manifest.json', 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        self.logger.info("Proceso completado")
        return all_results