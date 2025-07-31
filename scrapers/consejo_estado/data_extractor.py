# scrapers/consejo_estado/data_extractor.py
"""
Extractor de datos para el sistema SAMAI del Consejo de Estado
"""
from bs4 import BeautifulSoup
import re
import logging
from typing import List, Dict, Tuple, Optional


class SAMAIDataExtractor:
    """Extrae información de las páginas HTML de SAMAI"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def extraer_info_paginacion(self, html: str) -> Tuple[int, int]:
        """
        Extraer información de paginación del HTML

        Args:
            html: HTML de la página de resultados

        Returns:
            (total_resultados, resultados_por_pagina)
        """
        soup = BeautifulSoup(html, 'html.parser')

        # En SAMAI, la información de paginación viene en el texto general
        # Primero intentamos contar los resultados reales en la página
        tabla = soup.find('table', {'class': 'table'})
        if tabla:
            filas = tabla.find_all('tr')[1:]  # Saltar header
            resultados_en_pagina = len(filas)

            # Por defecto asumimos 10 por página
            # Si hay menos de 10, es probablemente la última página
            if resultados_en_pagina > 0:
                self.logger.info(f"Encontrados {resultados_en_pagina} resultados en la página")

                # Como no tenemos el total real, vamos a asumir un valor alto
                # y dejar que el proceso termine cuando no encuentre más resultados
                total_estimado = 1000  # Valor alto por defecto
                return total_estimado, 10

        # Si no encontramos tabla, intentar con el patrón de texto
        texto_completo = soup.get_text()

        # Buscar patrones comunes
        patterns = [
            r'Mostrando\s+(\d+)\s*-\s*(\d+)\s+de\s+(\d+)',
            r'(\d+)\s*-\s*(\d+)\s+de\s+(\d+)\s+resultado',
            r'Página\s+\d+\s+de\s+(\d+)',
            r'Total:\s*(\d+)\s+resultado'
        ]

        for pattern in patterns:
            match = re.search(pattern, texto_completo)
            if match:
                if len(match.groups()) == 3:
                    inicio = int(match.group(1))
                    fin = int(match.group(2))
                    total = int(match.group(3))
                    resultados_por_pagina = fin - inicio + 1
                    self.logger.info(
                        f"Información de paginación encontrada: {total} resultados, {resultados_por_pagina} por página")
                    return total, resultados_por_pagina
                elif len(match.groups()) == 1:
                    total = int(match.group(1))
                    self.logger.info(f"Total de resultados encontrado: {total}")
                    return total, 10

        # Si no encontramos información pero hay resultados, asumir valores
        if tabla and len(filas) > 0:
            self.logger.warning("No se encontró información de paginación, usando valores estimados")
            return 100, 10  # Valores por defecto más conservadores

        self.logger.warning("No se pudo extraer información de paginación ni resultados")
        return 0, 10

    def extraer_documentos_con_tokens(self, html: str) -> List[Dict]:
        """
        Extraer documentos y sus tokens JWT de la página de resultados

        Args:
            html: HTML de la página

        Returns:
            Lista de diccionarios con información de cada documento
        """
        soup = BeautifulSoup(html, 'html.parser')
        documentos = []
        documentos_procesados = set()  # Para evitar duplicados

        # Buscar la tabla de resultados
        tabla = soup.find('table', {'class': 'table'})
        if not tabla:
            self.logger.warning("No se encontró tabla de resultados")
            return documentos

        # Buscar todas las filas (excepto el header)
        filas = tabla.find_all('tr')[1:]  # Saltar el header

        self.logger.debug(f"Encontradas {len(filas)} filas en la tabla")

        for idx, fila in enumerate(filas):
            try:
                # Buscar el botón "Ver documento" con el token
                ver_doc_link = fila.find('a', onclick=re.compile(r'CargarVentana'))

                if not ver_doc_link:
                    self.logger.debug(f"Fila {idx + 1}: No se encontró botón 'Ver documento'")
                    continue

                onclick = ver_doc_link.get('onclick', '')

                # Extraer token del onclick
                token_match = re.search(r'tokenDocumento=([^\']+)', onclick)
                if not token_match:
                    self.logger.debug(f"Fila {idx + 1}: No se pudo extraer token")
                    continue
            except:
                self.logger.debug(f"Fila {idx + 1}: No se pudo extraer token")

    def extraer_documentos_con_tokens(self, html: str) -> List[Dict]:
        """
        Extraer documentos y sus tokens JWT de la página de resultados

        Args:
            html: HTML de la página

        Returns:
            Lista de diccionarios con información de cada documento
        """
        soup = BeautifulSoup(html, 'html.parser')
        documentos = []
        documentos_procesados = set()  # Para evitar duplicados

        # Método 1: Buscar todos los botones "Ver documento"
        ver_doc_links = soup.find_all('a', onclick=re.compile(r'CargarVentana'))

        self.logger.debug(f"Encontrados {len(ver_doc_links)} enlaces 'Ver documento'")

        for idx, link in enumerate(ver_doc_links):
            try:
                onclick = link.get('onclick', '')

                # Extraer token del onclick
                token_match = re.search(r'tokenDocumento=([^\'\"]+)', onclick)
                if not token_match:
                    self.logger.debug(f"Link {idx + 1}: No se pudo extraer token")
                    continue

                token = token_match.group(1)

                # Verificar si ya procesamos este documento
                if token in documentos_procesados:
                    self.logger.debug(f"Link {idx + 1}: Documento duplicado, omitiendo")
                    continue

                documentos_procesados.add(token)

                # Buscar el contenedor padre (puede ser div.row o tr)
                parent_container = link.find_parent('div', class_='row')
                if not parent_container:
                    parent_container = link.find_parent('tr')

                if not parent_container:
                    self.logger.debug(f"Link {idx + 1}: No se encontró contenedor padre")
                    # Aún así crear entrada con el token
                    doc_info = {'token': token}
                    documentos.append(doc_info)
                    continue

                # Crear diccionario para el documento
                doc_info = {
                    'token': token,
                    'numero_proceso': '',
                    'interno': '',
                    'fecha_proceso': '',
                    'fecha_providencia': '',
                    'clase_proceso': '',
                    'titular': '',
                    'sala_decision': '',
                    'tipo_providencia': '',
                    'actor': '',
                    'demandado': ''
                }

                # Extraer todos los spans con información
                spans = parent_container.find_all('span')

                for span in spans:
                    span_id = span.get('id', '')
                    span_text = span.text.strip()

                    if 'LblRadicado' in span_id:
                        doc_info['numero_proceso'] = span_text
                    elif 'LblInterno' in span_id:
                        doc_info['interno'] = span_text
                    elif 'LblFECHAPROC' in span_id:
                        doc_info['fecha_proceso'] = span_text
                    elif 'LblClaseProceso' in span_id:
                        doc_info['clase_proceso'] = span_text
                    elif 'LblPonente' in span_id:
                        doc_info['titular'] = span_text
                    elif 'LblActor' in span_id:
                        doc_info['actor'] = span_text
                    elif 'LbNombreSalaDecision' in span_id or 'LblNombreSalaDecision' in span_id:
                        doc_info['sala_decision'] = span_text
                    elif 'LblDemandado' in span_id:
                        doc_info['demandado'] = span_text
                    elif 'LblFechaProvidencia' in span_id:
                        doc_info['fecha_providencia'] = span_text
                    elif 'LblTipoProvidencia' in span_id:
                        doc_info['tipo_providencia'] = span_text

                # Agregar el documento
                documentos.append(doc_info)
                self.logger.debug(
                    f"Documento extraído: {doc_info.get('numero_proceso', 'Sin número')} - {doc_info.get('titular', 'Sin titular')}")

            except Exception as e:
                self.logger.error(f"Error procesando link {idx + 1}: {e}")
                continue

        # Si no encontramos documentos con el método anterior, intentar método alternativo
        if not documentos:
            self.logger.debug("No se encontraron documentos con el método principal, intentando método alternativo")

            # Buscar tabla de resultados
            tabla = soup.find('table', {'class': 'table'})
            if tabla:
                filas = tabla.find_all('tr')[1:]  # Saltar header

                for idx, fila in enumerate(filas):
                    # Buscar link en la fila
                    link = fila.find('a', onclick=re.compile(r'CargarVentana'))
                    if link:
                        onclick = link.get('onclick', '')
                        token_match = re.search(r'tokenDocumento=([^\'\"]+)', onclick)
                        if token_match:
                            token = token_match.group(1)
                            if token not in documentos_procesados:
                                doc_info = {'token': token}
                                # Intentar extraer más información de la fila
                                celdas = fila.find_all('td')
                                if len(celdas) > 1:
                                    doc_info['numero_proceso'] = celdas[0].text.strip() if celdas[0] else ''
                                documentos.append(doc_info)
                                documentos_procesados.add(token)

        self.logger.info(f"Total documentos extraídos: {len(documentos)}")

        return documentos

    def validar_documento(self, doc: Dict) -> bool:
        """
        Validar que un documento tenga la información mínima necesaria

        Args:
            doc: Diccionario con información del documento

        Returns:
            True si el documento es válido
        """
        # Debe tener al menos token y algún identificador
        if not doc.get('token'):
            return False

        if not (doc.get('numero_proceso') or doc.get('interno')):
            return False

        return True