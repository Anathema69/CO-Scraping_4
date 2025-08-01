import time
import json
from datetime import datetime
from pathlib import Path
import logging
from typing import List, Dict, Optional
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup


class ConsejoEstadoScraper:
    BASE_URL = "https://samai.consejodeestado.gov.co"
    SEARCH_URL = f"{BASE_URL}/TitulacionRelatoria/ResultadoBuscadorProvidenciasTituladas.aspx"
    VER_PROVIDENCIA_URL = f"{BASE_URL}/PaginasTransversales/VerProvidencia.aspx"

    def __init__(self):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = Path(f"logs/consejo_estado_{self.timestamp}")
        self.pdf_dir = Path("descargas_consejo_estado")
        self.manifest_path = self.log_dir / "manifest.json"
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
        # evitar duplicados
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file) for h in root_logger.handlers):
            root_logger.addHandler(file_handler)
        if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
            root_logger.addHandler(console_handler)

        self.logger = logging.getLogger(__name__)

    def save_manifest(self):
        with self.lock:
            try:
                with open(self.manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(self.all_results, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.logger.error(f"No se pudo guardar el manifiesto: {e}")

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

    def construir_url_busqueda(self, sala_decision: str, fecha_desde: str, fecha_hasta: str, pagina_actual: int = 0) -> str:
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

    def extraer_documentos_con_tokens(self, html: str, pagina: int) -> List[Dict]:
        soup = BeautifulSoup(html, 'html.parser')
        documentos = []

        # Busca los links que cargan ventana, de donde se extrae el token
        ver_doc_links = soup.find_all('a', onclick=re.compile(r'CargarVentana'))
        for idx, link in enumerate(ver_doc_links):
            try:
                onclick = link.get('onclick', '')
                token_match = re.search(r'tokenDocumento=([^\']+)', onclick)
                if not token_match:
                    continue
                token = token_match.group(1)

                # Buscar contenedor padre para campos adicionales
                parent = link.find_parent('div', class_='row') or link.find_parent('tr') or link
                doc_info = {
                    'token': token,
                    'numero_proceso': '',
                    'interno': '',
                    'fecha_proceso': '',
                    'clase_proceso': '',
                    'titular': '',
                    'sala_decision': '',
                    'fecha_providencia': '',
                    'tipo_providencia': '',
                    'actor': '',
                    'demandado': '',
                    # Descarga
                    'estado_descarga': None,  # null por defecto
                    'nombre_archivo': None,
                    'tamaño_archivo': None,
                    'error': None,
                    'ruta_zip': None,
                    'pagina': pagina,
                    'indice_en_pagina': idx,
                    'worker': None
                }

                # Radicado (número del proceso) desde el enlace correspondiente
                radicado_anchor = parent.find('a', id=re.compile(r'HypRadicado'))
                if radicado_anchor:
                    doc_info['numero_proceso'] = radicado_anchor.text.strip()

                # Interno
                interno = parent.find('span', id=re.compile(r'LblInterno'))
                if interno:
                    doc_info['interno'] = interno.text.strip()

                # Fecha proceso
                fecha_proc = parent.find('span', id=re.compile(r'LblFECHAPROC'))
                if fecha_proc:
                    doc_info['fecha_proceso'] = fecha_proc.text.strip()

                # Clase del proceso
                clase_proc = parent.find('span', id=re.compile(r'LblClaseProceso'))
                if clase_proc:
                    doc_info['clase_proceso'] = clase_proc.text.strip()

                # Titular / Ponente
                titular = parent.find('span', id=re.compile(r'LblPonente'))
                if titular:
                    doc_info['titular'] = titular.text.strip()

                # Sala de decisión
                sala = parent.find('span', id=re.compile(r'LbNombreSalaDecision'))
                if sala:
                    doc_info['sala_decision'] = sala.text.strip()

                # Actor
                actor = parent.find('span', id=re.compile(r'LblActor'))
                if actor:
                    doc_info['actor'] = actor.text.strip()

                # Demandado
                demandado = parent.find('span', id=re.compile(r'LblDemandado'))
                if demandado:
                    doc_info['demandado'] = demandado.text.strip()

                # Tipo de providencia
                tipo = parent.find('span', id=re.compile(r'LblTIPOPROVIDENCIA'))
                if tipo:
                    doc_info['tipo_providencia'] = tipo.text.strip()

                # Fecha de providencia (puede venir en otro span)
                providencia = parent.find('span', id=re.compile(r'Label1'))
                if providencia:
                    doc_info['fecha_providencia'] = providencia.text.strip()

                documentos.append(doc_info)
            except Exception as e:
                self.logger.warning(f"Error extrayendo documento en página {pagina}, índice {idx}: {e}")
                continue

        if not documentos:
            tabla = soup.find('table', {'class': 'table'})
            if tabla:
                filas = tabla.find_all('tr')[1:]
                for idx, fila in enumerate(filas):
                    link = fila.find('a', onclick=re.compile(r'CargarVentana'))
                    if link:
                        onclick = link.get('onclick', '')
                        token_match = re.search(r'tokenDocumento=([^\']+)', onclick)
                        if token_match:
                            token = token_match.group(1)
                            doc_info = {
                                'token': token,
                                'numero_proceso': '',
                                'interno': '',
                                'estado_descarga': None,
                                'nombre_archivo': None,
                                'tamaño_archivo': None,
                                'error': None,
                                'ruta_zip': None,
                                'pagina': pagina,
                                'indice_en_pagina': idx,
                                'worker': None
                            }
                            celdas = fila.find_all('td')
                            if len(celdas) >= 1:
                                doc_info['numero_proceso'] = celdas[0].text.strip()
                            documentos.append(doc_info)

        self.logger.info(f"Se extrajeron {len(documentos)} documentos en página {pagina}")
        return documentos

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
                debug_path = self.log_dir / f"debug_no_zip_{token[:8]}.html"
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                self.logger.error(f"No se encontró URL de descarga en la respuesta del token {token}")
                return None
        except Exception as e:
            self.logger.error(f"Error obteniendo URL de descarga ZIP para token {token}: {e}")
            return None

    def descargar_zip(self, url_descarga: str, numero_proceso: str) -> (Optional[str], int):
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

        self.logger.info(f"[Worker {threading.get_ident()}] Procesando documento {numero_proceso}")
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
            # Evita duplicados por token+indice: reemplaza si ya existe
            existing = next((r for r in self.all_results if r.get('token') == doc.get('token') and
                             r.get('indice_en_pagina') == doc.get('indice_en_pagina') and
                             r.get('pagina') == doc.get('pagina')), None)
            if existing:
                existing.update(doc)
            else:
                self.all_results.append(doc)
        self.save_manifest()
        self.logger.info(f"Registro actualizado: proceso {doc.get('numero_proceso')} estado={doc.get('estado_descarga')}")

    def search_and_download(self, filters: dict, download_pdfs: bool = True,
                            max_results: Optional[int] = None, max_workers: int = 3,
                            cancel_event: threading.Event = None) -> List[Dict]:
        start_time = datetime.now()
        self.logger.info("=" * 60)
        self.logger.info("INICIANDO SCRAPER CONSEJO DE ESTADO (con manifest y paralelo)")
        self.logger.info(f"Filtros: {json.dumps(filters, ensure_ascii=False)}")
        self.logger.info(f"Workers: {max_workers}, Descargar ZIPs: {download_pdfs}")
        self.logger.info(f"Límite de resultados: {max_results if max_results else 'sin límite'}")
        self.logger.info("=" * 60)

        sala = filters.get('sala_decision')
        fecha_desde = filters.get('fecha_desde')
        fecha_hasta = filters.get('fecha_hasta')

        if not all([sala, fecha_desde, fecha_hasta]):
            self.logger.error("Faltan filtros obligatorios (sala_decision, fecha_desde, fecha_hasta)")
            return []

        resultados_finales = []
        documentos_vistos = set()
        pagina = 0
        obtenidos = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []

            while True:
                if cancel_event and cancel_event.is_set():
                    self.logger.info("Cancelado por el usuario durante paginación")
                    break

                url_busqueda = self.construir_url_busqueda(sala, fecha_desde, fecha_hasta, pagina)
                self.logger.info(f"Obteniendo página {pagina}: {url_busqueda}")
                try:
                    response = self.session.get(url_busqueda, timeout=30)
                    response.raise_for_status()
                except Exception as e:
                    self.logger.error(f"Error obteniendo página {pagina}: {e}")
                    break

                documentos = self.extraer_documentos_con_tokens(response.text, pagina)
                if not documentos:
                    self.logger.info("No hay documentos en esta página, finalizando.")
                    break

                nuevos = []
                for d in documentos:
                    token = d.get('token')
                    key = (token, d.get('pagina'), d.get('indice_en_pagina'))
                    if token and key not in documentos_vistos:
                        documentos_vistos.add(key)
                        nuevos.append(d)

                if not nuevos:
                    self.logger.info("Todos los documentos de esta página ya fueron vistos.")
                    break

                for doc in nuevos:
                    if max_results and obtenidos >= max_results:
                        break
                    if download_pdfs:
                        futures.append(executor.submit(self.procesar_documento, doc))
                    else:
                        doc['estado_descarga'] = 'omitido'
                        self._register_result(doc)
                        resultados_finales.append(doc)
                        obtenidos += 1

                # Recolectar lo que ya terminó sin bloquear el siguiente page
                done_now = []
                for fut in list(futures):
                    if fut.done():
                        result = fut.result()
                        resultados_finales.append(result)
                        obtenidos += 1
                        done_now.append(fut)
                        if max_results and obtenidos >= max_results:
                            break
                for fut in done_now:
                    futures.remove(fut)

                if max_results and obtenidos >= max_results:
                    self.logger.info("Se alcanzó el límite solicitado.")
                    break

                pagina += 1
                time.sleep(0.3)  # cortesía

            # Esperar los pendientes
            for fut in as_completed(futures):
                if max_results and obtenidos >= max_results:
                    break
                result = fut.result()
                resultados_finales.append(result)
                obtenidos += 1

        elapsed = (datetime.now() - start_time).total_seconds()
        self.logger.info(f"Total procesados: {len(resultados_finales)} en {elapsed:.1f}s")
        return resultados_finales
