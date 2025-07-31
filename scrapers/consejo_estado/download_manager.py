# scrapers/consejo_estado/download_manager.py
"""
Gestor de descargas para el sistema SAMAI del Consejo de Estado
"""
import os
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
import requests


class SAMAIDownloadManager:
    """Gestiona las descargas de documentos ZIP de SAMAI"""

    def __init__(self, download_dir: Path):
        self.download_dir = download_dir
        self.download_dir.mkdir(exist_ok=True)
        self.logger = logging.getLogger(__name__)

        # URLs base
        self.base_url = "https://samai.consejodeestado.gov.co"
        self.ver_providencia_url = f"{self.base_url}/PaginasTransversales/VerProvidencia.aspx"

    def procesar_documento(self, doc_info: Dict, session: requests.Session) -> Dict:
        """
        Procesar un documento completo: previsualización → obtener URL → descargar

        Args:
            doc_info: Información del documento
            session: Sesión HTTP activa

        Returns:
            Diccionario con resultado de la descarga
        """
        resultado = {
            'exitoso': False,
            'archivo': None,
            'tamaño': 0,
            'error': None
        }

        posicion = doc_info.get('posicion_busqueda', 'N/A')
        numero_proceso = doc_info.get('numero_proceso', 'Sin número')

        self.logger.info(f"\n{'=' * 60}")
        self.logger.info(f"📄 Procesando documento en posición {posicion}")
        self.logger.info(f"Número proceso: {numero_proceso}")
        self.logger.info(f"Titular: {doc_info.get('titular', 'N/A')}")

        try:
            # Paso 1: Obtener página de previsualización
            self.logger.debug("1️⃣ Obteniendo página de previsualización...")
            html_providencia = self._obtener_pagina_providencia(doc_info['token'], session)

            if not html_providencia:
                resultado['error'] = "No se pudo obtener página de previsualización"
                self.logger.error(f"❌ {resultado['error']}")
                return resultado

            # Paso 2: Obtener URL de descarga
            self.logger.debug("2️⃣ Obteniendo URL de descarga del ZIP...")
            url_descarga = self._obtener_url_descarga_zip(doc_info['token'], html_providencia, session)

            if not url_descarga:
                resultado['error'] = "No se pudo obtener URL de descarga"
                self.logger.error(f"❌ {resultado['error']}")
                return resultado

            self.logger.debug(f"✅ URL obtenida: {url_descarga[:100]}...")

            # Paso 3: Descargar ZIP
            self.logger.debug("3️⃣ Descargando archivo ZIP...")
            archivo, tamaño = self._descargar_zip(url_descarga, numero_proceso, session)

            if archivo:
                resultado['exitoso'] = True
                resultado['archivo'] = archivo
                resultado['tamaño'] = tamaño
                self.logger.info(f"✅ Descarga exitosa: {archivo} ({tamaño:,} bytes)")
            else:
                resultado['error'] = "Error en la descarga del archivo"
                self.logger.error(f"❌ {resultado['error']}")

        except Exception as e:
            resultado['error'] = f"Error procesando documento: {str(e)}"
            self.logger.error(f"❌ {resultado['error']}", exc_info=True)

        return resultado

    def _obtener_pagina_providencia(self, token: str, session: requests.Session) -> Optional[str]:
        """Obtener la página de previsualización del documento"""
        url = f"{self.ver_providencia_url}?tokenDocumento={token}"

        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Sec-Fetch-Dest': 'iframe',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        }

        try:
            response = session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.logger.error(f"Error obteniendo página de providencia: {e}")
            return None

    def _obtener_url_descarga_zip(self, token: str, html_providencia: str,
                                  session: requests.Session) -> Optional[str]:
        """Obtener URL de descarga del ZIP haciendo POST en la página de providencia"""
        from bs4 import BeautifulSoup
        import re

        soup = BeautifulSoup(html_providencia, 'html.parser')

        # Extraer ViewState y EventValidation
        viewstate = soup.find('input', {'name': '__VIEWSTATE'})
        eventvalidation = soup.find('input', {'name': '__EVENTVALIDATION'})
        viewstategenerator = soup.find('input', {'name': '__VIEWSTATEGENERATOR'})

        if not all([viewstate, eventvalidation]):
            self.logger.error("No se encontraron tokens de estado necesarios")
            return None

        # Preparar datos para el POST
        post_data = {
            'ctl00$ContentPlaceHolder1$ScriptManager1': 'ctl00$ContentPlaceHolder1$PanelUpdate|ctl00$ContentPlaceHolder1$ZipLinkButton',
            '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$ZipLinkButton',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': viewstate.get('value', ''),
            '__VIEWSTATEGENERATOR': viewstategenerator.get('value', '') if viewstategenerator else '',
            '__EVENTVALIDATION': eventvalidation.get('value', ''),
            '__ASYNCPOST': 'true'
        }

        # Headers para el POST
        headers = {
            'Accept': '*/*',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-MicrosoftAjax': 'Delta=true',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': self.base_url,
            'Referer': f"{self.ver_providencia_url}?tokenDocumento={token}",
            'Cache-Control': 'no-cache'
        }

        try:
            # Hacer POST
            url = f"{self.ver_providencia_url}?tokenDocumento={token}"
            response = session.post(url, data=post_data, headers=headers, timeout=30)
            response.raise_for_status()

            # Buscar URL de descarga en el response
            match = re.search(
                r"window\.open\('(https://samaicore\.consejodeestado\.gov\.co/api/DescargarTitulacion/[^']+)'",
                response.text)

            if match:
                return match.group(1)
            else:
                self.logger.error("No se encontró URL de descarga en el response")
                # Guardar response para debugging
                debug_file = self.download_dir / f"debug_response_{token[:10]}.html"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                return None

        except Exception as e:
            self.logger.error(f"Error obteniendo URL de descarga: {e}")
            return None

    def _descargar_zip(self, url_descarga: str, numero_proceso: str,
                       session: requests.Session) -> Tuple[Optional[str], int]:
        """
        Descargar archivo ZIP desde la URL

        Returns:
            (nombre_archivo, tamaño) o (None, 0) si hay error
        """
        try:
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1'
            }

            response = session.get(url_descarga, headers=headers, timeout=60, stream=True)
            response.raise_for_status()

            # Generar nombre de archivo
            if numero_proceso and numero_proceso != 'Sin número':
                filename = f"{numero_proceso.replace('/', '_')}.zip"
            else:
                timestamp = int(time.time())
                filename = f"documento_{timestamp}.zip"

            filepath = self.download_dir / filename

            # Descargar por chunks
            total_size = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)

            # Verificar que el archivo no esté vacío
            if total_size == 0:
                os.remove(filepath)
                self.logger.error("Archivo descargado está vacío")
                return None, 0

            return filename, total_size

        except Exception as e:
            self.logger.error(f"Error descargando ZIP: {e}")
            return None, 0