# scrapers/consejo_estado/session_manager.py
"""
Gestor de sesiones para el sistema SAMAI del Consejo de Estado
"""
import requests
import json
import urllib.parse
from datetime import datetime
import logging
from typing import Optional, Tuple


class SAMAISessionManager:
    """Maneja las sesiones y peticiones HTTP para SAMAI"""

    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://samai.consejodeestado.gov.co"
        self.search_url = f"{self.base_url}/TitulacionRelatoria/ResultadoBuscadorProvidenciasTituladas.aspx"
        self.ver_providencia_url = f"{self.base_url}/PaginasTransversales/VerProvidencia.aspx"
        self.logger = logging.getLogger(__name__)

        # Headers básicos
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'Accept-Language': 'es-ES,es;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Origin': self.base_url,
            'Referer': self.base_url
        })

    def construir_filtro_odata(self, sala_decision: str, fecha_desde: str, fecha_hasta: str) -> str:
        """
        Construir el filtro OData para la búsqueda

        Args:
            sala_decision: Nombre de la sala (ej: "Sección Cuarta")
            fecha_desde: Fecha inicio en formato DD/MM/YYYY
            fecha_hasta: Fecha fin en formato DD/MM/YYYY

        Returns:
            Filtro OData formateado
        """
        # Convertir fechas
        fecha_desde_obj = datetime.strptime(fecha_desde, '%d/%m/%Y')
        fecha_hasta_obj = datetime.strptime(fecha_hasta, '%d/%m/%Y')

        # Formato para OData (ISO 8601)
        fecha_desde_str = fecha_desde_obj.strftime('%Y-%m-%dT00:00:00.000Z')
        fecha_hasta_str = fecha_hasta_obj.strftime('%Y-%m-%dT23:59:59.999Z')

        # Construir filtro
        filtro = f"( NombreSalaDecision eq '{sala_decision}') and " \
                 f"( FechaProvidencia ge {fecha_desde_str} and FechaProvidencia le {fecha_hasta_str})"

        self.logger.debug(f"Filtro OData construido: {filtro}")

        return filtro

    def construir_url_busqueda(self, sala_decision: str, fecha_desde: str,
                               fecha_hasta: str, pagina_actual: int = 0) -> str:
        """
        Construir la URL completa de búsqueda

        Args:
            sala_decision: Nombre de la sala
            fecha_desde: Fecha inicio DD/MM/YYYY
            fecha_hasta: Fecha fin DD/MM/YYYY
            pagina_actual: Número de página (0-indexed)

        Returns:
            URL completa de búsqueda
        """
        filtro = self.construir_filtro_odata(sala_decision, fecha_desde, fecha_hasta)

        # Diccionario de búsqueda
        busqueda_dict = {
            "corporacion": "1100103",  # Código del Consejo de Estado
            "modo": "2",
            "filtro": filtro,
            "busqueda": "",
            "searchMode": "all",
            "orderby": "FechaProvidencia desc",
            "PaginaActual": str(pagina_actual)
        }

        # Convertir a JSON y codificar
        json_str = json.dumps(busqueda_dict, separators=(',', ':'))
        encoded = urllib.parse.quote(json_str)

        url = f"{self.search_url}?BusquedaDictionary={encoded}&"

        self.logger.info(f"URL construida para página {pagina_actual + 1}")
        self.logger.debug(f"URL completa: {url}")

        return url

    def obtener_pagina(self, url: str, timeout: int = 30) -> Optional[str]:
        """
        Obtener el HTML de una página

        Args:
            url: URL a obtener
            timeout: Tiempo máximo de espera

        Returns:
            HTML de la página o None si hay error
        """
        try:
            self.logger.debug(f"Obteniendo página: {url[:100]}...")

            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()

            self.logger.debug(f"Respuesta recibida: {response.status_code}, {len(response.text)} bytes")

            return response.text

        except requests.exceptions.Timeout:
            self.logger.error(f"Timeout obteniendo página")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error obteniendo página: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error inesperado: {e}")
            return None

    def obtener_pagina_providencia(self, token: str) -> Optional[str]:
        """
        Obtener la página de previsualización de un documento

        Args:
            token: Token JWT del documento

        Returns:
            HTML de la página o None si hay error
        """
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
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.logger.error(f"Error obteniendo página de providencia: {e}")
            return None

    def obtener_url_descarga_zip(self, token: str, html_providencia: str) -> Optional[str]:
        """
        Obtener URL de descarga del ZIP desde la página de providencia

        Args:
            token: Token JWT del documento
            html_providencia: HTML de la página de providencia

        Returns:
            URL de descarga o None si hay error
        """
        from bs4 import BeautifulSoup
        import re

        soup = BeautifulSoup(html_providencia, 'html.parser')

        # Extraer tokens necesarios
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
            response = self.session.post(url, data=post_data, headers=headers, timeout=30)
            response.raise_for_status()

            # Buscar URL de descarga en el response
            match = re.search(
                r"window\.open\('(https://samaicore\.consejodeestado\.gov\.co/api/DescargarTitulacion/[^']+)'",
                response.text)

            if match:
                return match.group(1)
            else:
                self.logger.error("No se encontró URL de descarga en el response")
                return None

        except Exception as e:
            self.logger.error(f"Error obteniendo URL de descarga: {e}")
            return None