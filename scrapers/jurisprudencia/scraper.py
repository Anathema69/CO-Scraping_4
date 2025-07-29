# scrapers/jurisprudencia/scraper.py
"""
Scraper de Jurisprudencia - Versión simplificada
Mantiene una sola sesión y descarga todo de manera secuencial con workers paralelos
"""
import requests
from urllib.parse import unquote
import re
from datetime import datetime
import time
import csv
import json
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import List, Dict, Optional, Tuple

# Configuración
BASE_URL = "https://consultajurisprudencial.ramajudicial.gov.co"
INDEX_URL = f"{BASE_URL}/WebRelatoria/csj/index.xhtml"
PDF_URL = f"{BASE_URL}/WebRelatoria/FileReferenceServlet"

# Headers comunes
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'es-ES,es;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
}


class JudicialScraperV2:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = Path(f"logs/{self.timestamp}")
        self.pdf_dir = Path("descargas_pdf")
        self.setup_directories()
        self.setup_logging()

        # Estado
        self.viewstate = None
        self.download_queue = []
        self.results_lock = threading.Lock()
        self.all_results = []
        self.processed_ids = set()

        # Configuración
        self.max_tema_length = 200
        self.download_timeout = 60
        self.max_retries = 3

    def setup_directories(self):
        """Crear directorios necesarios"""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(exist_ok=True)

    def setup_logging(self):
        """Configurar sistema de logging"""
        log_file = self.log_dir / "descarga.log"

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logging.basicConfig(
            level=logging.INFO,
            handlers=[file_handler, console_handler]
        )

        self.logger = logging.getLogger(__name__)

    def extract_viewstate(self, html_content: str) -> Optional[str]:
        """Extrae el ViewState del HTML"""
        pattern = r'<input type="hidden" name="javax\.faces\.ViewState".*?value="([^"]+)"'
        match = re.search(pattern, html_content)
        return match.group(1) if match else None

    def clean_tema(self, tema_text: str) -> str:
        """Limpia y trunca el texto del tema"""
        if not tema_text:
            return ""

        # Limpiar HTML
        tema = tema_text.replace('<br>', ' ').replace('<b>', '').replace('</b>', '')
        tema = re.sub(r'<[^>]+>', '', tema).strip()

        # Cortar en el primer delimitador
        for delimiter in [' - ', '\n', '|', '•']:
            if delimiter in tema:
                tema = tema.split(delimiter)[0].strip()
                break

        # Truncar si es muy largo
        if len(tema) > self.max_tema_length:
            tema = tema[:self.max_tema_length] + "..."

        return tema

    def extract_jurisprudence_data(self, html_content: str) -> List[Dict]:
        """Extrae todos los datos de jurisprudencia del HTML"""
        data = []

        # Extraer contenido CDATA
        cdata_pattern = r'<!\[CDATA\[(.*?)\]\]>'
        cdata_matches = re.findall(cdata_pattern, html_content, re.DOTALL)

        for cdata in cdata_matches:
            if 'ID:' in cdata and 'PROCESO:' in cdata:
                record = self._extract_record_from_cdata(cdata)

                if record and record.get('id'):
                    # Verificar duplicados
                    if record['id'] not in self.processed_ids:
                        self.processed_ids.add(record['id'])
                        data.append(record)
                        self.logger.debug(
                            f"Extraído: ID={record['id']}, Providencia={record.get('numero_providencia', 'N/A')}")

        return data

    def _extract_record_from_cdata(self, cdata: str) -> Optional[Dict]:
        """Extrae un registro individual del contenido CDATA"""
        try:
            record = {
                'nombre_archivo': None,
                'estado_descarga': 'pendiente',
                'intentos': 0,
                'error': None,
                'tamaño_archivo': None,
                'fecha_descarga': None
            }

            # ID (requerido)
            id_match = re.search(r'ID:\s*</b></font><font[^>]*>(\d+)', cdata)
            if not id_match:
                return None
            record['id'] = id_match.group(1)

            # Número de proceso
            proceso_match = re.search(r'PROCESO:\s*</b></font><font[^>]*>([^<]+)', cdata)
            record['numero_proceso'] = proceso_match.group(1).strip() if proceso_match else ''

            # Número de providencia
            providencia_match = re.search(r'PROVIDENCIA:\s*</b></font><font[^>]*>([^<]+)', cdata)
            record['numero_providencia'] = providencia_match.group(1).strip() if providencia_match else ''

            # Clase de actuación
            actuacion_match = re.search(r'ACTUACI[ÓO]N:\s*</b></font><font[^>]*>([^<]+)', cdata)
            record['clase_actuacion'] = actuacion_match.group(1).strip() if actuacion_match else ''

            # Tipo de providencia
            tipo_match = re.search(r'TIPO DE PROVIDENCIA:\s*</b></font><font[^>]*>([^<]+)', cdata)
            record['tipo_providencia'] = tipo_match.group(1).strip() if tipo_match else ''

            # Fecha
            fecha_match = re.search(r'FECHA:\s*</b></font><font[^>]*>([^<]+)', cdata)
            record['fecha'] = fecha_match.group(1).strip() if fecha_match else ''

            # Ponente
            ponente_match = re.search(r'PONENTE:\s*</b></font><font[^>]*>([^<]+)', cdata)
            record['ponente'] = ponente_match.group(1).strip() if ponente_match else ''

            # Tema (con limpieza)
            tema_match = re.search(r'TEMA:\s*</b></font><font[^>]*>(.*?)</font>', cdata, re.DOTALL)
            if tema_match:
                record['tema'] = self.clean_tema(tema_match.group(1))
            else:
                record['tema'] = ''

            # Fuente formal
            fuente_match = re.search(r'FUENTE FORMAL:\s*</b></font><font[^>]*>(.*?)</font>', cdata, re.DOTALL)
            if fuente_match:
                fuente = fuente_match.group(1).replace('<br>', ' ')
                fuente = re.sub(r'<[^>]+>', '', fuente).strip()
                record['fuente_formal'] = fuente[:500] if len(fuente) > 500 else fuente
            else:
                record['fuente_formal'] = ''

            return record

        except Exception as e:
            self.logger.error(f"Error extrayendo registro: {e}")
            return None

    def get_filename_from_cd(self, disposition: Optional[str], doc_id: str) -> str:
        """Extrae nombre de archivo de Content-Disposition"""
        if not disposition:
            return f"{doc_id}.pdf"

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

    def download_pdf_worker(self, record: Dict) -> Tuple[bool, str]:
        """Worker para descargar un PDF"""
        doc_id = record['id']

        # Crear sesión temporal para esta descarga
        session = requests.Session()
        session.headers.update(HEADERS)

        for attempt in range(self.max_retries):
            try:
                pdf_params = {
                    'corp': 'csj',
                    'ext': 'pdf',
                    'file': doc_id
                }

                response = session.get(
                    PDF_URL,
                    params=pdf_params,
                    timeout=self.download_timeout,
                    stream=True
                )

                if response.status_code == 200:
                    # Obtener nombre del archivo
                    content_disposition = response.headers.get('Content-Disposition')
                    filename = self.get_filename_from_cd(content_disposition, doc_id)

                    # Descargar contenido
                    content = b''
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            content += chunk

                    # Validar PDF
                    if len(content) < 1000 or not content.startswith(b'%PDF'):
                        raise Exception("Archivo no válido o muy pequeño")

                    # Guardar archivo
                    filepath = self.pdf_dir / filename
                    with open(filepath, 'wb') as f:
                        f.write(content)

                    # Actualizar registro
                    with self.results_lock:
                        record['nombre_archivo'] = filename
                        record['estado_descarga'] = 'completado'
                        record['tamaño_archivo'] = len(content)
                        record['fecha_descarga'] = datetime.now().isoformat()

                    self.logger.info(f"✅ Descargado: {filename} ({len(content):,} bytes)")
                    return True, f"Descargado: {filename}"
                else:
                    raise Exception(f"HTTP {response.status_code}")

            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                else:
                    error_msg = str(e)
                    with self.results_lock:
                        record['error'] = error_msg
                        record['estado_descarga'] = 'error'
                    self.logger.error(f"❌ Error descargando {doc_id}: {error_msg}")
                    return False, error_msg
            finally:
                session.close()

    def navigate_to_next(self, viewstate: str) -> Tuple[bool, Optional[str]]:
        """Navegar a la siguiente página"""
        try:
            ajax_headers = HEADERS.copy()
            ajax_headers.update({
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Faces-Request': 'partial/ajax',
                'Accept': 'application/xml, text/xml, */*; q=0.01',
                'Origin': BASE_URL,
                'Referer': INDEX_URL,
            })

            nav_params = {
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': 'resultForm:j_idt259',  # Botón siguiente
                'javax.faces.partial.execute': '@all',
                'javax.faces.partial.render': 'resultForm:jurisTable resultForm:pagText2',
                'resultForm:j_idt259': 'resultForm:j_idt259',
                'resultForm': 'resultForm',
                'resultForm:jurisTable_selection': '',
                'javax.faces.ViewState': viewstate
            }

            response = self.session.post(
                INDEX_URL,
                data=nav_params,
                headers=ajax_headers,
                timeout=30
            )

            if response.status_code == 200:
                # Actualizar ViewState
                new_viewstate = self.extract_viewstate(response.text)
                if new_viewstate:
                    self.viewstate = new_viewstate
                return True, response.text
            else:
                return False, None

        except Exception as e:
            self.logger.error(f"Error en navegación: {e}")
            return False, None

    def search_and_download_with_params(self, search_params: dict, download_pdfs: bool = True,
                                        max_results: Optional[int] = None, max_workers: int = 3,
                                        cancel_event=None, **kwargs) -> Optional[List[Dict]]:
        """
        Función principal que realiza búsqueda y descarga

        Args:
            search_params: Parámetros de búsqueda del formulario
            download_pdfs: Si descargar los PDFs
            max_results: Límite máximo de resultados
            max_workers: Número de workers para descargas paralelas
            cancel_event: Evento de cancelación
            **kwargs: Ignorar parámetros adicionales de la versión segmentada
        """
        start_time = datetime.now()

        # Logging inicial
        fecha_inicio = search_params.get('searchForm:fechaIniCal', 'N/A')
        fecha_fin = search_params.get('searchForm:fechaFinCal', 'N/A')

        self.logger.info("=" * 70)
        self.logger.info("🚀 INICIANDO SCRAPER JUDICIAL SIMPLIFICADO")
        self.logger.info("=" * 70)
        self.logger.info(f"📅 Período: {fecha_inicio} - {fecha_fin}")
        self.logger.info(f"👥 Workers: {max_workers}")
        self.logger.info(f"📥 Descargar PDFs: {download_pdfs}")
        self.logger.info(f"🎯 Límite resultados: {max_results if max_results else 'Sin límite'}")

        try:
            # Fase 1: Obtener página inicial y ViewState
            self.logger.info("\n📡 FASE 1: Obteniendo página inicial...")
            response = self.session.get(INDEX_URL, timeout=30)
            if response.status_code != 200:
                self.logger.error(f"Error obteniendo página inicial: {response.status_code}")
                return None

            self.viewstate = self.extract_viewstate(response.text)
            if not self.viewstate:
                self.logger.error("No se pudo extraer ViewState")
                return None

            # Headers AJAX para todas las peticiones
            ajax_headers = HEADERS.copy()
            ajax_headers.update({
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Faces-Request': 'partial/ajax',
                'Accept': 'application/xml, text/xml, */*; q=0.01',
                'Origin': BASE_URL,
                'Referer': INDEX_URL,
            })

            # Fase 2: Realizar búsqueda
            self.logger.info("\n🔍 FASE 2: Realizando búsqueda...")

            # Actualizar ViewState en parámetros
            formatted_params = search_params.copy()
            formatted_params['javax.faces.ViewState'] = self.viewstate

            # Formatear campos especiales
            if 'searchForm:tipoInput' in formatted_params and formatted_params['searchForm:tipoInput']:
                tipo_value = formatted_params['searchForm:tipoInput']
                # Si ya tiene comillas dobles, no agregar más
                if not (tipo_value.startswith('"') and tipo_value.endswith('"')):
                    formatted_params['searchForm:tipoInput'] = f'"{tipo_value}"'

            if 'searchForm:temaInput' in formatted_params and formatted_params['searchForm:temaInput']:
                tema_value = formatted_params['searchForm:temaInput']
                # Si ya tiene comillas dobles, no agregar más
                if not (tema_value.startswith('"') and tema_value.endswith('"')):
                    formatted_params['searchForm:temaInput'] = f'"{tema_value}"'

            # Realizar búsqueda
            response = self.session.post(
                INDEX_URL,
                data=formatted_params,
                headers=ajax_headers,
                timeout=45
            )

            if response.status_code != 200:
                self.logger.error(f"Error en búsqueda: HTTP {response.status_code}")
                return None

            # Obtener total de resultados
            results_pattern = r'Resultado:\s*(\d+)\s*/\s*(\d+)'
            match = re.search(results_pattern, response.text)
            if not match:
                self.logger.error("No se pudo determinar el número de resultados")
                return None

            current_result = int(match.group(1))
            total_results = int(match.group(2))

            if max_results and max_results < total_results:
                total_results = max_results

            self.logger.info(f"📊 Resultados encontrados: {total_results}")

            # Guardar manifiesto
            self.save_manifest(formatted_params, total_results)

            # Verificar cancelación
            if cancel_event and cancel_event.is_set():
                return None

            # Fase 3: Recolectar y descargar
            self.logger.info("\n🔄 FASE 3: Recolectando datos y descargando PDFs...")

            if download_pdfs:
                # Usar ThreadPoolExecutor para descargas paralelas
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {}
                    pages_processed = 0

                    # Procesar primera página
                    page_data = self.extract_jurisprudence_data(response.text)
                    self.all_results.extend(page_data)

                    # Programar descargas de la primera página
                    for record in page_data:
                        future = executor.submit(self.download_pdf_worker, record)
                        futures[future] = record['id']

                    pages_processed += 1
                    self.logger.info(f"📄 Página 1: {len(page_data)} registros")

                    # Navegar por páginas restantes
                    while len(self.all_results) < total_results:
                        # Verificar cancelación
                        if cancel_event and cancel_event.is_set():
                            self.logger.info("🛑 Proceso cancelado por el usuario")
                            break

                        # Navegar a siguiente página
                        success, html = self.navigate_to_next(self.viewstate)

                        if not success:
                            self.logger.error(f"Error navegando a página {pages_processed + 1}")
                            break

                        # Extraer datos
                        page_data = self.extract_jurisprudence_data(html)

                        if not page_data:
                            self.logger.warning(f"Sin datos en página {pages_processed + 1}")
                        else:
                            self.all_results.extend(page_data)

                            # Programar descargas
                            for record in page_data:
                                future = executor.submit(self.download_pdf_worker, record)
                                futures[future] = record['id']

                            pages_processed += 1
                            self.logger.info(
                                f"📄 Página {pages_processed}: {len(page_data)} registros, "
                                f"Total: {len(self.all_results)}/{total_results}"
                            )

                        # Guardar progreso cada 50 registros
                        if len(self.all_results) % 50 == 0:
                            self.save_results(self.all_results)

                        # Pausa entre navegación
                        time.sleep(0.8)

                    # Esperar descargas pendientes
                    self.logger.info("\n⏳ Esperando descargas pendientes...")
                    completed = 0
                    for future in as_completed(futures):
                        completed += 1
                        doc_id = futures[future]

                        try:
                            success, msg = future.result()
                            if not success:
                                self.logger.warning(f"Descarga fallida {doc_id}: {msg}")
                        except Exception as e:
                            self.logger.error(f"Excepción en descarga {doc_id}: {e}")

                        if completed % 10 == 0:
                            self.logger.info(f"Progreso descargas: {completed}/{len(futures)}")

            else:
                # Solo recolectar metadatos sin descargar
                page_data = self.extract_jurisprudence_data(response.text)
                self.all_results.extend(page_data)
                pages_processed = 1

                while len(self.all_results) < total_results:
                    if cancel_event and cancel_event.is_set():
                        break

                    success, html = self.navigate_to_next(self.viewstate)
                    if not success:
                        break

                    page_data = self.extract_jurisprudence_data(html)
                    if page_data:
                        self.all_results.extend(page_data)
                        pages_processed += 1
                        self.logger.info(f"Página {pages_processed}: {len(page_data)} registros")

                    time.sleep(0.5)

            # Fase 4: Guardar resultados finales
            self.logger.info("\n💾 FASE 4: Guardando resultados finales...")
            self.save_results(self.all_results)

            # Generar reporte final
            report = self.generate_final_report(self.all_results, start_time)

            # Logging final
            elapsed_time = (datetime.now() - start_time).total_seconds()
            self.logger.info("\n" + "=" * 70)
            self.logger.info("✅ PROCESO COMPLETADO EXITOSAMENTE")
            self.logger.info(f"⏱️  Tiempo total: {elapsed_time:.1f} segundos")
            self.logger.info(f"📄 Documentos procesados: {len(self.all_results)}")
            if download_pdfs:
                completed = sum(1 for r in self.all_results if r.get('estado_descarga') == 'completado')
                self.logger.info(f"📥 PDFs descargados: {completed}")
            self.logger.info("=" * 70)

            return self.all_results

        except Exception as e:
            self.logger.error(f"❌ Error crítico: {e}", exc_info=True)
            return None

    def save_manifest(self, search_params: dict, total_results: int):
        """Guardar manifiesto inicial"""
        manifest = {
            'timestamp': self.timestamp,
            'fecha_busqueda': datetime.now().isoformat(),
            'parametros_busqueda': search_params,
            'total_resultados_esperados': total_results,
            'estado': 'iniciado',
            'estrategia': 'simple',
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

        self.logger.info(f"📋 Manifiesto guardado en: {manifest_path}")

    def save_results(self, results: List[Dict]):
        """Guardar resultados en JSON y CSV"""
        # JSON completo
        json_path = self.log_dir / 'resultados_completos.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # CSV
        if results:
            csv_path = self.log_dir / f'jurisprudencia_{self.timestamp}.csv'
            csv_fields = [
                'id', 'numero_providencia', 'numero_proceso', 'fecha',
                'ponente', 'tipo_providencia', 'clase_actuacion',
                'tema', 'nombre_archivo', 'estado_descarga', 'error'
            ]

            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(results)

        self.logger.debug(f"💾 Resultados guardados: {len(results)} registros")

    def generate_final_report(self, results: List[Dict], start_time: datetime) -> dict:
        """Generar reporte final detallado"""
        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()

        total_recolectados = len(results)
        total_descargados = sum(1 for r in results if r.get('estado_descarga') == 'completado')
        total_errores = sum(1 for r in results if r.get('estado_descarga') == 'error')
        total_pendientes = sum(1 for r in results if r.get('estado_descarga') == 'pendiente')

        report = {
            'resumen': {
                'total_recolectados': total_recolectados,
                'total_descargados': total_descargados,
                'total_errores': total_errores,
                'total_pendientes': total_pendientes,
                'tasa_exito': f"{(total_descargados / total_recolectados * 100):.2f}%" if total_recolectados > 0 else "0%",
                'tiempo_total_segundos': elapsed,
                'tiempo_total_formateado': f"{int(elapsed // 60)}m {int(elapsed % 60)}s",
                'estrategia_usada': 'simple'
            },
            'registros_con_error': [
                                       {
                                           'id': r['id'],
                                           'numero_providencia': r.get('numero_providencia', ''),
                                           'error': r.get('error', '')
                                       }
                                       for r in results if r.get('estado_descarga') == 'error'
                                   ][:20],  # Limitar a 20
            'tiempo_ejecucion': {
                'inicio': start_time.isoformat(),
                'fin': end_time.isoformat(),
                'duracion': str(end_time - start_time)
            }
        }

        # Guardar reporte
        report_path = self.log_dir / 'reporte_final.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Actualizar manifiesto
        manifest_path = self.log_dir / 'manifest.json'
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            manifest['estado'] = 'completado'
            manifest['fecha_fin'] = end_time.isoformat()
            manifest['total_resultados_reales'] = total_recolectados

            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

        # Mostrar resumen
        print("\n" + "=" * 60)
        print("📊 REPORTE FINAL")
        print("=" * 60)
        print(f"Total recolectados: {total_recolectados}")
        print(f"Total descargados:  {total_descargados}")
        print(f"Total con errores:  {total_errores}")
        print(f"Total pendientes:   {total_pendientes}")
        print(f"Tasa de éxito:      {report['resumen']['tasa_exito']}")
        print(f"Tiempo total:       {report['resumen']['tiempo_total_formateado']}")
        print("=" * 60)

        return report