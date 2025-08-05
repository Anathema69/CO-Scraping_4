import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
import re
from pathlib import Path
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse, parse_qs, quote
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter


class CCBArbitrajeScraper:
    def __init__(self, output_dir: str = "descargas_biblioteca", log_dir: str = None,
                 timestamp: str = None, max_workers: int = 5):
        # Usar timestamp proporcionado o generar uno nuevo
        self.timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")

        # Configurar directorios siguiendo el patrón de otros scrapers
        self.base_url = "https://bibliotecadigital.ccb.org.co"
        self.browse_url = f"{self.base_url}/browse/dateissued"
        self.browse_author_url = f"{self.base_url}/browse/author"
        self.scope = "66633b37-c004-4701-9685-446a1d42c06d"

        # Directorio de descargas (PDFs)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.pdf_dir = self.output_dir  # Los PDFs van directamente aquí

        # Directorio de logs
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = Path(f"logs/biblioteca_ccb_{self.timestamp}")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.max_workers = max_workers

        # Configurar logging
        log_format = '%(asctime)s - %(levelname)s - %(message)s'

        # Handler para archivo con UTF-8
        log_file = self.log_dir / 'biblioteca_ccb_scraping.log'
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(log_format))

        # Handler para consola con encoding seguro
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(log_format))

        # Configurar logger específico para esta instancia
        self.logger = logging.getLogger(f'CCBScraper_{self.timestamp}')
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()  # Limpiar handlers anteriores
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        # Configurar sesión con timeouts más largos
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/html, */*',
            'Accept-Language': 'es-ES,es;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br'
        })

        # Retry strategy para manejar errores transitorios
        retry_strategy = Retry(
            total=5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Archivo de progreso en el directorio de logs
        self.progress_file = self.log_dir / "progress.json"
        self.metadata_file = self.log_dir / "laudos_metadata.csv"
        self.manifest_file = self.log_dir / "manifest.json"
        self.load_progress()

        # Crear manifiesto inicial
        self.create_manifest()

    def create_manifest(self):
        """Crear o actualizar el manifiesto del proceso"""
        manifest = {
            'timestamp': self.timestamp,
            'fecha_inicio': datetime.now().isoformat(),
            'estado': 'iniciado',
            'parametros': {
                'output_dir': str(self.output_dir),
                'log_dir': str(self.log_dir)
            },
            'archivos_generados': {
                'log': str(self.log_dir / 'biblioteca_ccb_scraping.log'),
                'metadata_csv': str(self.metadata_file),
                'progress': str(self.progress_file),
                'carpeta_pdfs': str(self.output_dir)
            }
        }

        with open(self.manifest_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def update_manifest(self, estado='en_proceso', adicional=None):
        """Actualizar el manifiesto con el estado actual"""
        if self.manifest_file.exists():
            with open(self.manifest_file, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        else:
            manifest = {}

        manifest['estado'] = estado
        manifest['ultima_actualizacion'] = datetime.now().isoformat()

        if adicional:
            manifest.update(adicional)

        with open(self.manifest_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def load_progress(self):
        """Carga el progreso previo si existe"""
        if self.progress_file.exists():
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                self.progress = json.load(f)

            # Limpiar duplicados en downloaded
            self.progress['downloaded'] = list(set(self.progress['downloaded']))

            self.logger.info(f"Progreso cargado: {len(self.progress['downloaded'])} laudos descargados")
        else:
            self.progress = {
                'downloaded': [],
                'failed': [],
                'last_offset': 0,
                'total_items': 0
            }

    def save_progress(self):
        """Guarda el progreso actual"""
        # Limpiar duplicados antes de guardar
        self.progress['downloaded'] = list(set(self.progress['downloaded']))
        self.progress['failed'] = list(set(self.progress['failed']))

        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(self.progress, f, indent=2)

    def parse_tribunal_title(self, title: str) -> Dict[str, str]:
        """Extrae demandante y demandado del título"""
        # Patrón básico: TRIBUNAL ARBITRAL DE [DEMANDANTE] VS. [DEMANDADO]
        pattern = r'TRIBUNAL ARBITRAL DE (.+?) VS\.? (.+?)$'
        match = re.match(pattern, title, re.IGNORECASE)

        if match:
            return {
                'demandante': match.group(1).strip(),
                'demandado': match.group(2).strip()
            }
        else:
            # Intentar patrón alternativo sin "TRIBUNAL ARBITRAL DE"
            pattern2 = r'^(.+?) VS\.? (.+?)$'
            match2 = re.match(pattern2, title, re.IGNORECASE)
            if match2:
                return {
                    'demandante': match2.group(1).strip(),
                    'demandado': match2.group(2).strip()
                }

        return {'demandante': '', 'demandado': ''}

    def get_page_items(self, page: int = 1, rpp: int = 20, starts_with: str = None,
                       browse_type: str = 'dateissued', author_value: str = None) -> Tuple[List[str], int]:
        """
        Obtiene los IDs de items de una página usando bbm.page y bbm.rpp para paginación

        Args:
            page: número de página (1-indexed)
            rpp: Resultados por página (20 o 100)
            starts_with: Filtro de fecha (ej: "2024" o "2023-04")
            browse_type: Tipo de búsqueda ('dateissued' o 'author')
            author_value: Nombre del autor para búsqueda por autor

        Returns:
            Tupla de (lista de IDs, total de items)
        """
        params = {
            'scope': self.scope,
            'bbm.rpp': rpp,
            'bbm.page': page,
            'sort_by': '2',
            'order': 'ASC',
            'etal': '-1',
        }

        # Configurar URL y parámetros según el tipo de búsqueda
        if browse_type == 'author':
            url = self.browse_author_url
            if author_value:
                params['value'] = author_value
                params['bbm.return'] = '1'  # Necesario para búsqueda por autor
        else:
            url = self.browse_url
            if starts_with:
                params['startsWith'] = starts_with
                self.logger.info(f"Aplicando filtro de fecha: {starts_with}")

        timeout_seconds = 60 if rpp > 20 else 30

        try:
            self.logger.debug(f"Solicitando página {page} con rpp={rpp}, tipo={browse_type}")
            response = self.session.get(url, params=params, timeout=timeout_seconds)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Extraer IDs de items únicos
            item_ids = []
            seen_ids = set()
            item_links = soup.find_all('a', href=re.compile(r'/items/([a-f0-9\-]+)'))
            for link in item_links:
                match = re.search(r'/items/([a-f0-9\-]+)', link.get('href', ''))
                if match:
                    item_id = match.group(1)
                    if item_id not in seen_ids:
                        seen_ids.add(item_id)
                        item_ids.append(item_id)

            # Obtener el total de resultados
            total_items = 0
            results_text = soup.find(string=re.compile(r'Mostrando \d+ - \d+ de \d+'))
            if results_text:
                match = re.search(r'de (\d+)', str(results_text))
                if match:
                    total_items = int(match.group(1))
                    self.logger.info(f"Total de items encontrados: {total_items}")

            self.logger.info(f"Items en esta página: {len(item_ids)} (page={page}, rpp={rpp})")
            return item_ids, total_items

        except requests.Timeout:
            self.logger.error(f"Timeout al obtener página (page={page}, rpp={rpp})")
            return [], 0
        except Exception as e:
            self.logger.error(f"Error obteniendo página (page={page}): {str(e)}")
            return [], 0

    def get_authors_list(self, letter: str = None) -> List[Dict[str, any]]:
        """
        Obtiene la lista de autores disponibles

        Args:
            letter: Letra inicial para filtrar autores (opcional)

        Returns:
            Lista de diccionarios con nombre del autor y cantidad de documentos
        """
        authors = []

        params = {
            'scope': self.scope,
            'bbm.rpp': 100  # Máximo para reducir paginación
        }

        if letter:
            params['startsWith'] = letter

        try:
            response = self.session.get(self.browse_author_url, params=params, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Buscar la tabla de autores
            author_table = soup.find('table', class_='table')
            if author_table:
                rows = author_table.find_all('tr')[1:]  # Saltar header

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        author_link = cols[0].find('a')
                        if author_link:
                            author_name = author_link.text.strip()
                            # Extraer cantidad del segundo td
                            count_text = cols[1].text.strip()
                            try:
                                count = int(count_text)
                            except:
                                count = 0

                            authors.append({
                                'nombre': author_name,
                                'cantidad': count
                            })

            self.logger.info(f"Encontrados {len(authors)} autores")
            return authors

        except Exception as e:
            self.logger.error(f"Error obteniendo lista de autores: {str(e)}")
            return []

    def get_item_metadata(self, item_id: str) -> Optional[Dict]:
        """Obtiene metadatos de un item usando el API REST"""
        api_url = f"{self.base_url}/server/api/core/items/{item_id}"

        try:
            response = self.session.get(api_url, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Extraer metadatos relevantes
            metadata = {
                'id': item_id,
                'handle': data.get('handle', ''),
                'name': data.get('name', ''),
                'lastModified': data.get('lastModified', ''),
                'archived': data.get('inArchive', False)
            }

            # Procesar campos de metadatos
            dc_metadata = data.get('metadata', {})

            # Autores/Árbitros
            authors = dc_metadata.get('dc.contributor.author', [])
            metadata['arbitros'] = '; '.join([author['value'] for author in authors])

            # Fecha
            dates = dc_metadata.get('dc.date.issued', [])
            metadata['fecha'] = dates[0]['value'] if dates else ''

            # Descripción
            descriptions = dc_metadata.get('dc.description.abstract', [])
            metadata['descripcion'] = descriptions[0]['value'] if descriptions else ''

            # Materia
            subjects = dc_metadata.get('dc.subject', [])
            metadata['materias'] = '; '.join([subject['value'] for subject in subjects])

            # Extraer demandante y demandado del título
            partes = self.parse_tribunal_title(metadata['name'])
            metadata.update(partes)

            # Obtener información de bitstreams (archivos)
            metadata['bitstreams'] = self.get_item_bitstreams(item_id)

            return metadata

        except Exception as e:
            self.logger.error(f"Error obteniendo metadatos del item {item_id}: {str(e)}")
            return None

    def get_item_bitstreams(self, item_id: str) -> List[Dict]:
        """Obtiene información de los archivos asociados al item"""
        bundles_url = f"{self.base_url}/server/api/core/items/{item_id}/bundles"

        try:
            response = self.session.get(bundles_url, timeout=30)
            response.raise_for_status()

            bundles_data = response.json()
            bitstreams = []

            if '_embedded' in bundles_data and 'bundles' in bundles_data['_embedded']:
                for bundle in bundles_data['_embedded']['bundles']:
                    if bundle.get('name') == 'ORIGINAL':
                        bundle_uuid = bundle.get('uuid')
                        if bundle_uuid:
                            bundle_bitstreams_url = f"{self.base_url}/server/api/core/bundles/{bundle_uuid}/bitstreams"
                            bs_response = self.session.get(bundle_bitstreams_url, timeout=30)

                            if bs_response.status_code == 200:
                                bs_data = bs_response.json()
                                if '_embedded' in bs_data and 'bitstreams' in bs_data['_embedded']:
                                    for bitstream in bs_data['_embedded']['bitstreams']:
                                        bitstream_uuid = bitstream.get('uuid')
                                        bitstream_detail_url = f"{self.base_url}/server/api/core/bitstreams/{bitstream_uuid}"

                                        mime_type = 'application/pdf'
                                        size_bytes = 0

                                        try:
                                            detail_response = self.session.get(bitstream_detail_url, timeout=10)
                                            if detail_response.status_code == 200:
                                                detail_data = detail_response.json()
                                                mime_type = detail_data.get('mimeType', mime_type)
                                                size_bytes = detail_data.get('sizeBytes', 0)
                                        except:
                                            pass

                                        bitstreams.append({
                                            'id': bitstream_uuid,
                                            'name': bitstream.get('name', ''),
                                            'sizeBytes': size_bytes,
                                            'mimeType': mime_type,
                                            'download_url': f"{self.base_url}/bitstreams/{bitstream_uuid}/download"
                                        })

            return bitstreams

        except Exception as e:
            self.logger.error(f"Error obteniendo bitstreams del item {item_id}: {str(e)}")
            return []

    def download_pdf(self, bitstream_info: Dict, item_metadata: Dict) -> bool:
        """Descarga un archivo PDF"""
        try:
            # Crear nombre de archivo seguro
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', item_metadata['name'])[:200]
            fecha = item_metadata.get('fecha', 'sin_fecha')
            filename = f"{fecha}_{safe_name}.pdf"
            filepath = self.pdf_dir / filename

            # Si ya existe, no descargar de nuevo
            if filepath.exists():
                self.logger.info(f"Archivo ya existe: {filename}")
                return True

            # Descargar archivo con manejo de redirecciones
            response = self.session.get(
                bitstream_info['download_url'],
                stream=True,
                timeout=60,
                allow_redirects=True
            )
            response.raise_for_status()

            # Verificar que sea un PDF
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower() and not response.content[:4] == b'%PDF':
                self.logger.warning(f"El archivo no parece ser un PDF: {content_type}")
                if not filename.lower().endswith('.pdf'):
                    return False

            # Guardar archivo
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            size_mb = downloaded / 1024 / 1024
            self.logger.info(f"Descargado: {filename} ({size_mb:.2f} MB)")
            return True

        except Exception as e:
            self.logger.error(f"Error descargando PDF {bitstream_info['id']}: {str(e)}")
            return False

    def process_item(self, item_id: str) -> bool:
        """Procesa un item completo: metadatos y descarga"""
        # Verificar si ya fue procesado
        if item_id in self.progress['downloaded']:
            self.logger.debug(f"Item ya procesado: {item_id}")
            return True

        if item_id in self.progress['failed']:
            self.logger.info(f"Reintentando item fallido: {item_id}")

        try:
            # Obtener metadatos
            metadata = self.get_item_metadata(item_id)
            if not metadata:
                if item_id not in self.progress['failed']:
                    self.progress['failed'].append(item_id)
                return False

            # Descargar PDFs
            pdf_downloaded = False
            for bitstream in metadata['bitstreams']:
                is_pdf = (
                        bitstream.get('mimeType', '').lower() == 'application/pdf' or
                        bitstream.get('name', '').lower().endswith('.pdf')
                )

                if is_pdf:
                    if self.download_pdf(bitstream, metadata):
                        pdf_downloaded = True
                        break

            # Guardar metadatos
            self.save_metadata(metadata)

            # Actualizar progreso
            if pdf_downloaded:
                if item_id not in self.progress['downloaded']:
                    self.progress['downloaded'].append(item_id)
                if item_id in self.progress['failed']:
                    self.progress['failed'].remove(item_id)
            else:
                if item_id not in self.progress['failed']:
                    self.progress['failed'].append(item_id)

            self.save_progress()

            # Pequeña pausa para no sobrecargar el servidor
            time.sleep(0.5)

            return pdf_downloaded

        except Exception as e:
            self.logger.error(f"Error procesando item {item_id}: {str(e)}")
            if item_id not in self.progress['failed']:
                self.progress['failed'].append(item_id)
            return False

    def save_metadata(self, metadata: Dict):
        """Guarda metadatos en CSV"""
        file_exists = self.metadata_file.exists()

        with open(self.metadata_file, 'a', newline='', encoding='utf-8') as f:
            fieldnames = [
                'id', 'handle', 'name', 'fecha', 'demandante', 'demandado',
                'arbitros', 'materias', 'descripcion', 'archived', 'lastModified'
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()

            # Preparar fila sin información de bitstreams
            row = {k: metadata.get(k, '') for k in fieldnames}
            writer.writerow(row)

    def run(self, limit: int = None, rpp: int = 20, date_filter: str = None,
            browse_type: str = 'dateissued', author_filter: str = None):
        """
        Ejecuta el scraper completo

        Args:
            limit: Número máximo de items a procesar (None = todos)
            rpp: Resultados por página (20 o 100)
            date_filter: Filtro de fecha (ej: "2024" o "2023-04")
            browse_type: Tipo de búsqueda ('dateissued' o 'author')
            author_filter: Nombre del autor para búsqueda por autor
        """
        self.logger.info("=== INICIANDO SCRAPER CCB ARBITRAJE NACIONAL ===")
        self.logger.info(f"Items ya descargados: {len(self.progress['downloaded'])}")
        self.logger.info(f"Items fallidos: {len(self.progress['failed'])}")

        if limit:
            self.logger.info(f"LÍMITE ESTABLECIDO: {limit} items")

        if browse_type == 'dateissued' and date_filter:
            self.logger.info(f"FILTRO DE FECHA: {date_filter}")
        elif browse_type == 'author' and author_filter:
            self.logger.info(f"BÚSQUEDA POR AUTOR: {author_filter}")

        self.logger.info(f"Resultados por página: {rpp}")

        # Actualizar manifiesto
        self.update_manifest('en_proceso', {
            'parametros_busqueda': {
                'tipo': browse_type,
                'filtro': date_filter or author_filter,
                'limite': limit,
                'rpp': rpp
            }
        })

        # Obtener todos los IDs de items
        all_item_ids = []
        seen_ids = set()
        page = 1
        total_items = 0

        while True:
            self.logger.info(f"Obteniendo página {page}")

            if browse_type == 'author':
                item_ids, page_total = self.get_page_items(
                    page, rpp, browse_type='author', author_value=author_filter
                )
            else:
                item_ids, page_total = self.get_page_items(
                    page, rpp, starts_with=date_filter
                )

            if page_total > 0 and total_items == 0:
                total_items = page_total
                self.progress['total_items'] = total_items

                if limit is not None and limit > total_items:
                    self.logger.info(
                        f"Límite inicial {limit} mayor que total_items {total_items}, ajustando a {total_items}"
                    )
                    limit = total_items

            if not item_ids:
                if page == 1:
                    self.logger.warning("No se encontraron items con los filtros especificados")
                break

            for item_id in item_ids:
                if item_id not in seen_ids:
                    seen_ids.add(item_id)
                    all_item_ids.append(item_id)

            if limit and len(all_item_ids) >= limit:
                all_item_ids = all_item_ids[:limit]
                self.logger.info(f"Límite alcanzado: {len(all_item_ids)} items")
                break

            if len(item_ids) < rpp:
                break

            if total_items and len(all_item_ids) >= total_items:
                break

            page += 1
            time.sleep(1)

        self.logger.info(f"Total de items únicos encontrados: {len(all_item_ids)}")

        # Filtrar items ya procesados exitosamente
        items_to_process = [
            item_id for item_id in all_item_ids
            if item_id not in self.progress['downloaded']
        ]

        if limit and len(items_to_process) > limit:
            items_to_process = items_to_process[:limit]

        self.logger.info(f"Items por procesar: {len(items_to_process)}")

        if not items_to_process:
            self.logger.info("No hay nuevos items para procesar")
            self.update_manifest('completado', {
                'fecha_fin': datetime.now().isoformat(),
                'resumen': self.get_summary()
            })
            return

        # Procesar items en paralelo
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.process_item, item_id): item_id
                for item_id in items_to_process
            }

            completed = 0
            for future in as_completed(futures):
                completed += 1
                item_id = futures[future]

                try:
                    success = future.result()
                    status = "[OK]" if success else "[FAIL]"
                    self.logger.info(
                        f"[{completed}/{len(items_to_process)}] {status} Procesado: {item_id}"
                    )
                except Exception as e:
                    self.logger.error(f"Error en thread para {item_id}: {str(e)}")

                # Guardar progreso cada 10 items
                if completed % 10 == 0:
                    self.save_progress()

        # Guardar progreso final
        self.save_progress()

        # Actualizar manifiesto final
        resumen = self.get_summary()
        self.update_manifest('completado', {
            'fecha_fin': datetime.now().isoformat(),
            'resumen': resumen
        })

        # Generar reporte final
        self.generate_final_report()

        # Resumen final
        self.logger.info("=== RESUMEN FINAL ===")
        self.logger.info(f"Total procesados exitosamente: {len(self.progress['downloaded'])}")
        self.logger.info(f"Fallidos: {len(self.progress['failed'])}")
        self.logger.info(f"Metadatos guardados en: {self.metadata_file}")
        self.logger.info(f"PDFs guardados en: {self.pdf_dir}")

        if self.progress['failed']:
            self.logger.info("Items fallidos:")
            for item_id in self.progress['failed'][:10]:
                self.logger.info(f"  - {item_id}")
            if len(self.progress['failed']) > 10:
                self.logger.info(f"  ... y {len(self.progress['failed']) - 10} más")

    def get_summary(self):
        """Obtiene resumen del proceso"""
        return {
            'total_esperados': self.progress.get('total_items', 0),
            'total_procesados': len(self.progress['downloaded']) + len(self.progress['failed']),
            'descargados': len(self.progress['downloaded']),
            'fallidos': len(self.progress['failed']),
            'tasa_exito': (len(self.progress['downloaded']) /
                           (len(self.progress['downloaded']) + len(self.progress['failed'])) * 100)
            if (len(self.progress['downloaded']) + len(self.progress['failed'])) > 0 else 0
        }

    def generate_final_report(self):
        """Genera reporte final en JSON"""
        report = {
            'timestamp': self.timestamp,
            'fecha_ejecucion': datetime.now().isoformat(),
            'filtros_aplicados': {
                'tipo': 'fecha' if hasattr(self, 'date_filter') else 'autor',
                'valor': getattr(self, 'date_filter', getattr(self, 'author_filter', None))
            },
            'resumen': self.get_summary(),
            'archivos_generados': {
                'metadata_csv': str(self.metadata_file),
                'progress_json': str(self.progress_file),
                'manifest_json': str(self.manifest_file),
                'log': str(self.log_dir / 'biblioteca_ccb_scraping.log')
            }
        }

        report_path = self.log_dir / 'reporte_final.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Reporte final guardado en: {report_path}")