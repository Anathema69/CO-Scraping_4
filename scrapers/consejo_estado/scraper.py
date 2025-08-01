# scrapers/consejo_estado/scraper.py
import time
import json
import csv
from datetime import datetime
from pathlib import Path
import logging
from typing import List, Dict, Optional, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from .data_extractor import SAMAIDataExtractor


class ConsejoEstadoScraper:
    BASE_URL = "https://samai.consejodeestado.gov.co"
    SEARCH_URL = f"{BASE_URL}/TitulacionRelatoria/ResultadoBuscadorProvidenciasTituladas.aspx"
    VER_PROVIDENCIA_URL = f"{BASE_URL}/PaginasTransversales/VerProvidencia.aspx"

    def __init__(self):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = Path(f"logs/consejo_estado_{self.timestamp}")
        self.pdf_dir = Path("descargas_consejo_estado")
        self.manifest_path = self.log_dir / "manifest.json"
        self.csv_path = self.log_dir / f"consejo_estado_resultados_{self.timestamp}.csv"
        self.report_path = self.log_dir / "reporte_final.json"

        self.setup_directories()
        self.setup_logging()

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'es-ES,es;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
        })

        self.all_results: List[Dict] = []
        self.lock = threading.Lock()
        self.start_time = None
        self.total_esperados = 0
        self.data_extractor = SAMAIDataExtractor()

    def setup_directories(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(exist_ok=True)

    def setup_logging(self):
        log_file = self.log_dir / "consejo_estado_scraping.log"
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        # Evitar duplicados
        root_logger.handlers.clear()
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

        self.logger = logging.getLogger(__name__)

    def save_manifest(self):
        """Guardar manifiesto JSON actualizado"""
        with self.lock:
            try:
                manifest_data = {
                    'timestamp': self.timestamp,
                    'total_esperados': self.total_esperados,
                    'total_procesados': len(self.all_results),
                    'estado': 'en_proceso',
                    'resultados': self.all_results
                }
                with open(self.manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(manifest_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.logger.error(f"Error guardando manifiesto: {e}")

    def save_csv(self):
        """Guardar resultados en formato CSV"""
        with self.lock:
            try:
                with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                    if not self.all_results:
                        return

                    # Definir campos del CSV
                    fieldnames = [
                        'pagina', 'indice_en_pagina', 'numero_proceso', 'interno',
                        'fecha_proceso', 'fecha_providencia', 'clase_proceso',
                        'tipo_providencia', 'titular', 'sala_decision', 'actor',
                        'demandado', 'estado_descarga', 'nombre_archivo',
                        'tamaño_archivo', 'error', 'token'
                    ]

                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()

                    for result in self.all_results:
                        # Crear fila con solo los campos definidos
                        row = {field: result.get(field, '') for field in fieldnames}
                        writer.writerow(row)

                self.logger.info(f"CSV guardado: {self.csv_path}")
            except Exception as e:
                self.logger.error(f"Error guardando CSV: {e}")

    def obtener_total_resultados(self, sala_decision: str, fecha_desde: str, fecha_hasta: str) -> int:
        """Obtener el total de resultados esperados para los filtros dados"""
        try:
            url = self.construir_url_busqueda(sala_decision, fecha_desde, fecha_hasta, 0)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Buscar el span que contiene el total
            total_label = soup.find('span', {'id': 'ContentPlaceHolder1_LblCantidadTotal'})
            if total_label:
                total_text = total_label.text.strip()
                # Extraer número del texto
                total_match = re.search(r'\d+', total_text)
                if total_match:
                    return int(total_match.group())

            # Si no encontramos el label específico, usar el extractor
            total, _ = self.data_extractor.extraer_info_paginacion(response.text)
            return total

        except Exception as e:
            self.logger.error(f"Error obteniendo total de resultados: {e}")
            return 0

    def construir_filtro_odata(self, sala_decision: str, fecha_desde: str, fecha_hasta: str) -> str:
        try:
            fecha_desde_obj = datetime.strptime(fecha_desde, '%d/%m/%Y')
            fecha_hasta_obj = datetime.strptime(fecha_hasta, '%d/%m/%Y')
            fecha_desde_str = fecha_desde_obj.strftime('%Y-%m-%dT00:00:00.000Z')
            fecha_hasta_str = fecha_hasta_obj.strftime('%Y-%m-%dT00:00:00.000Z')
        except ValueError:
            self.logger.warning("Formato de fecha inesperado, se asumirá tal cual.")
            fecha_desde_str = fecha_desde
            fecha_hasta_str = fecha_hasta

        filtro = f"( NombreSalaDecision eq '{sala_decision}') and " \
                 f"( FechaProvidencia ge {fecha_desde_str} and FechaProvidencia le {fecha_hasta_str})"
        return filtro

    def construir_url_busqueda(self, sala_decision: str, fecha_desde: str, fecha_hasta: str,
                               pagina_actual: int = 0) -> str:
        filtro = self.construir_filtro_odata(sala_decision, fecha_desde, fecha_hasta)
        busqueda_dict = {
            "corporacion": "1100103",
            "modo": "2",
            "filtro": filtro,
            "busqueda": "",
            "searchMode": "all",
            "orderby": "FechaProvidencia desc",
            "PaginaActual": str(pagina_actual)
        }
        json_str = json.dumps(busqueda_dict, separators=(',', ':'))
        encoded = urllib.parse.quote(json_str)
        return f"{self.SEARCH_URL}?BusquedaDictionary={encoded}&"

    def obtener_pagina_providencia(self, token: str) -> Optional[str]:
        url = f"{self.VER_PROVIDENCIA_URL}?tokenDocumento={token}"
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Sec-Fetch-Dest': 'iframe',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }
        try:
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.logger.error(f"Error obteniendo página de providencia para token {token}: {e}")
            return None

    def obtener_url_descarga_zip(self, token: str, html_providencia: str) -> Optional[str]:
        soup = BeautifulSoup(html_providencia, 'html.parser')
        viewstate = soup.find('input', {'name': '__VIEWSTATE'})
        eventvalidation = soup.find('input', {'name': '__EVENTVALIDATION'})
        viewstategenerator = soup.find('input', {'name': '__VIEWSTATEGENERATOR'})

        if not (viewstate and eventvalidation):
            self.logger.error("No se encontraron los tokens __VIEWSTATE/__EVENTVALIDATION necesarios")
            return None

        post_data = {
            'ctl00$ContentPlaceHolder1$ScriptManager1': 'ctl00$ContentPlaceHolder1$PanelUpdate|ctl00$ContentPlaceHolder1$ZipLinkButton',
            '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$ZipLinkButton',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': viewstate.get('value', ''),
            '__VIEWSTATEGENERATOR': viewstategenerator.get('value', '') if viewstategenerator else '',
            '__EVENTVALIDATION': eventvalidation.get('value', ''),
            '__ASYNCPOST': 'true'
        }

        headers = {
            'Accept': '*/*',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-MicrosoftAjax': 'Delta=true',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': self.BASE_URL,
            'Referer': f"{self.VER_PROVIDENCIA_URL}?tokenDocumento={token}",
            'Cache-Control': 'no-cache'
        }

        try:
            url = f"{self.VER_PROVIDENCIA_URL}?tokenDocumento={token}"
            response = self.session.post(url, data=post_data, headers=headers, timeout=30)
            response.raise_for_status()

            match = re.search(
                r"window\.open\('(https://samaicore\.consejodeestado\.gov\.co/api/DescargarTitulacion/[^']+)'",
                response.text)
            if match:
                return match.group(1)
            else:
                self.logger.error(f"No se encontró URL de descarga en la respuesta del token {token}")
                return None
        except Exception as e:
            self.logger.error(f"Error obteniendo URL de descarga ZIP para token {token}: {e}")
            return None

    def descargar_zip(self, url_descarga: str, numero_proceso: str) -> Tuple[Optional[str], int]:
        try:
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1'
            }
            response = self.session.get(url_descarga, headers=headers, timeout=60, stream=True)
            response.raise_for_status()

            if numero_proceso and numero_proceso.strip():
                filename = f"{numero_proceso.replace('/', '_')}.zip"
            else:
                filename = f"documento_{int(time.time())}.zip"

            filepath = self.pdf_dir / filename
            total_size = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)

            if total_size == 0:
                if filepath.exists():
                    filepath.unlink()
                self.logger.error(f"ZIP descargado está vacío para proceso {numero_proceso}")
                return None, 0

            return filename, total_size
        except Exception as e:
            self.logger.error(f"Error descargando ZIP para proceso {numero_proceso}: {e}")
            return None, 0

    def procesar_documento(self, doc: Dict) -> Dict:
        token = doc.get('token')
        numero_proceso = doc.get('numero_proceso') or doc.get('interno', 'Sin número')

        if not token:
            doc['estado_descarga'] = 'error'
            doc['error'] = 'Falta token'
            return doc

        self.logger.info(f"[Worker {threading.get_ident()}] Procesando {numero_proceso}")
        doc['worker'] = threading.get_ident()

        html_providencia = self.obtener_pagina_providencia(token)
        if not html_providencia:
            doc['estado_descarga'] = 'error'
            doc['error'] = 'No se pudo obtener página de providencia'
            self._register_result(doc)
            return doc

        url_zip = self.obtener_url_descarga_zip(token, html_providencia)
        if not url_zip:
            doc['estado_descarga'] = 'error'
            doc['error'] = 'No se encontró URL de descarga ZIP'
            self._register_result(doc)
            return doc

        doc['ruta_zip'] = url_zip
        nombre, tamaño = self.descargar_zip(url_zip, numero_proceso)
        if nombre:
            doc['estado_descarga'] = 'descargado'
            doc['nombre_archivo'] = nombre
            doc['tamaño_archivo'] = tamaño
        else:
            doc['estado_descarga'] = 'error'
            doc['error'] = 'Error descargando ZIP'

        self._register_result(doc)
        return doc

    def _register_result(self, doc: Dict):
        with self.lock:
            # Evitar duplicados por token+indice
            existing = next((r for r in self.all_results if
                             r.get('token') == doc.get('token') and
                             r.get('indice_en_pagina') == doc.get('indice_en_pagina') and
                             r.get('pagina') == doc.get('pagina')), None)
            if existing:
                existing.update(doc)
            else:
                self.all_results.append(doc)

        # Guardar manifiesto y CSV actualizados
        self.save_manifest()
        self.save_csv()

        self.logger.info(f"Registro actualizado: {doc.get('numero_proceso')} - Estado: {doc.get('estado_descarga')}")

    def generar_reporte_final(self):
        """Generar reporte final con estadísticas"""
        try:
            duracion = (datetime.now() - datetime.fromisoformat(
                self.start_time)).total_seconds() if self.start_time else 0

            # Calcular estadísticas
            total_documentos = len(self.all_results)
            descargados = sum(1 for d in self.all_results if d.get('estado_descarga') == 'descargado')
            errores = sum(1 for d in self.all_results if d.get('estado_descarga') == 'error')
            omitidos = sum(1 for d in self.all_results if d.get('estado_descarga') == 'omitido')

            # Calcular tamaño total
            tamaño_total = sum(d.get('tamaño_archivo', 0) for d in self.all_results if d.get('tamaño_archivo'))

            reporte = {
                'timestamp': self.timestamp,
                'fecha_inicio': self.start_time,
                'fecha_fin': datetime.now().isoformat(),
                'duracion_segundos': duracion,
                'duracion_formateada': f"{int(duracion // 60)}m {int(duracion % 60)}s",
                'resumen': {
                    'total_esperados': self.total_esperados,
                    'total_documentos': total_documentos,
                    'pdfs_descargados': descargados,
                    'errores_descarga': errores,
                    'omitidos': omitidos,
                    'tamaño_total_bytes': tamaño_total,
                    'tamaño_total_mb': round(tamaño_total / (1024 * 1024), 2) if tamaño_total > 0 else 0
                },
                'estadisticas_por_tipo': {
                    'descargados': descargados,
                    'errores': errores,
                    'omitidos': omitidos
                },
                'archivos_generados': {
                    'log': str(self.log_dir / 'consejo_estado_scraping.log'),
                    'csv': str(self.csv_path),
                    'manifest': str(self.manifest_path)
                }
            }

            # Guardar reporte
            with open(self.report_path, 'w', encoding='utf-8') as f:
                json.dump(reporte, f, ensure_ascii=False, indent=2)

            # Actualizar manifiesto con estado final
            with self.lock:
                manifest_data = {
                    'timestamp': self.timestamp,
                    'total_esperados': self.total_esperados,
                    'total_procesados': total_documentos,
                    'estado': 'completado',
                    'reporte_final': reporte,
                    'resultados': self.all_results
                }
                with open(self.manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(manifest_data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"Reporte final generado: {self.report_path}")
            return reporte

        except Exception as e:
            self.logger.error(f"Error generando reporte final: {e}")
            return None

    def search_and_download(self, filters: dict, download_pdfs: bool = True,
                            max_results: Optional[int] = None, max_workers: int = 3,
                            cancel_event: threading.Event = None) -> List[Dict]:
        """
        Buscar y descargar documentos del Consejo de Estado

        Args:
            filters: Diccionario con sala_decision, fecha_desde, fecha_hasta
            download_pdfs: Si descargar los ZIPs
            max_results: Límite de resultados (None = sin límite)
            max_workers: Número de workers paralelos
            cancel_event: Evento para cancelar el proceso

        Returns:
            Lista de resultados procesados
        """
        self.start_time = datetime.now().isoformat()
        start_time = datetime.now()

        self.logger.info("=" * 60)
        self.logger.info("INICIANDO SCRAPER CONSEJO DE ESTADO")
        self.logger.info(f"Filtros: {json.dumps(filters, ensure_ascii=False)}")
        self.logger.info(f"Workers: {max_workers}, Descargar ZIPs: {download_pdfs}")
        self.logger.info(f"Límite de resultados: {max_results if max_results else 'sin límite'}")
        self.logger.info("=" * 60)

        sala = filters.get('sala_decision')
        fecha_desde = filters.get('fecha_desde')
        fecha_hasta = filters.get('fecha_hasta')

        if not all([sala, fecha_desde, fecha_hasta]):
            self.logger.error("Faltan filtros obligatorios")
            return []

        # Obtener total de resultados esperados
        self.total_esperados = self.obtener_total_resultados(sala, fecha_desde, fecha_hasta)
        self.logger.info(f"Total de documentos esperados: {self.total_esperados}")

        if self.total_esperados == 0:
            self.logger.warning("No se encontraron documentos con los filtros especificados")
            self.generar_reporte_final()
            return []

        # Guardar manifiesto inicial
        self.save_manifest()

        resultados_finales = []
        documentos_vistos = set()
        pagina = 0
        obtenidos = 0
        todos_documentos = []  # Recolectar todos los documentos primero

        # FASE 1: Recolectar todos los documentos
        self.logger.info("FASE 1: Recolectando información de documentos...")

        while True:
            if cancel_event and cancel_event.is_set():
                self.logger.info("Cancelado por el usuario durante recolección")
                break

            if max_results and obtenidos >= max_results:
                self.logger.info("Se alcanzó el límite de resultados solicitado")
                break

            url_busqueda = self.construir_url_busqueda(sala, fecha_desde, fecha_hasta, pagina)
            self.logger.info(f"Obteniendo página {pagina + 1}")

            try:
                response = self.session.get(url_busqueda, timeout=30)
                response.raise_for_status()
            except Exception as e:
                self.logger.error(f"Error obteniendo página {pagina}: {e}")
                break

            documentos = self.data_extractor.extraer_documentos_con_tokens(response.text)

            if not documentos:
                self.logger.info("No hay más documentos, finalizando recolección")
                break

            # Actualizar página e índice para cada documento
            for idx, doc in enumerate(documentos):
                doc['pagina'] = pagina + 1
                doc['indice_en_pagina'] = idx + 1

            nuevos = []
            for d in documentos:
                token = d.get('token')
                key = (token, d.get('pagina'), d.get('indice_en_pagina'))
                if token and key not in documentos_vistos:
                    documentos_vistos.add(key)
                    nuevos.append(d)
                    obtenidos += 1

                    if max_results and obtenidos >= max_results:
                        break

            todos_documentos.extend(nuevos)

            if not nuevos:
                self.logger.info("Todos los documentos de esta página ya fueron vistos")
                break

            self.logger.info(f"Página {pagina + 1}: {len(nuevos)} documentos nuevos recolectados")

            pagina += 1
            time.sleep(0.3)  # Cortesía entre peticiones

        self.logger.info(f"FASE 1 completada: {len(todos_documentos)} documentos recolectados")

        # FASE 2: Procesar descargas en paralelo
        if download_pdfs and todos_documentos:
            self.logger.info(f"FASE 2: Descargando {len(todos_documentos)} documentos con {max_workers} workers...")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []

                for doc in todos_documentos:
                    if cancel_event and cancel_event.is_set():
                        break

                    future = executor.submit(self.procesar_documento, doc)
                    futures.append(future)

                # Procesar resultados conforme se completan
                for future in as_completed(futures):
                    if cancel_event and cancel_event.is_set():
                        self.logger.info("Cancelado por el usuario durante descargas")
                        break

                    try:
                        result = future.result()
                        resultados_finales.append(result)
                    except Exception as e:
                        self.logger.error(f"Error procesando documento: {e}")
        else:
            # Si no se descargan PDFs, marcar como omitidos
            for doc in todos_documentos:
                doc['estado_descarga'] = 'omitido'
                self._register_result(doc)
                resultados_finales.append(doc)

        # Generar reporte final
        elapsed = (datetime.now() - start_time).total_seconds()
        self.logger.info(f"Proceso completado en {elapsed:.1f} segundos")

        reporte = self.generar_reporte_final()

        if reporte:
            self.logger.info("=" * 60)
            self.logger.info("RESUMEN FINAL:")
            self.logger.info(f"Total esperados: {reporte['resumen']['total_esperados']}")
            self.logger.info(f"Total procesados: {reporte['resumen']['total_documentos']}")
            self.logger.info(f"Descargados: {reporte['resumen']['pdfs_descargados']}")
            self.logger.info(f"Errores: {reporte['resumen']['errores_descarga']}")
            self.logger.info(f"Tamaño total: {reporte['resumen']['tamaño_total_mb']} MB")
            self.logger.info(f"Duración: {reporte['duracion_formateada']}")
            self.logger.info("=" * 60)

        return resultados_finales