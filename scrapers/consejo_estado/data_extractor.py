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

        # Buscar el span que contiene el total de documentos
        total_label = soup.find('span', {'id': lambda x: x and 'LblCantidadTotal' in x})
        if total_label:
            try:
                total_text = total_label.text.strip()
                total_match = re.search(r'\d+', total_text)
                if total_match:
                    total = int(total_match.group())
                    self.logger.info(f"Total de documentos encontrados: {total}")
                    return total, 10
            except:
                pass

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

        # Buscar todos los botones "Ver documento"
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

                # Buscar el contenedor principal más externo (div.row)
                parent_container = None

                # Subir en el DOM hasta encontrar el div.row principal
                current = link
                for _ in range(10):  # Buscar hasta 10 niveles arriba
                    current = current.parent
                    if current and current.name == 'div' and 'row' in current.get('class', []):
                        # Verificar que este div.row contenga los campos que necesitamos
                        if current.find('a', id=re.compile(r'.*HypRadicado.*')):
                            parent_container = current
                            break

                if not parent_container:
                    self.logger.debug(f"Link {idx + 1}: No se encontró contenedor padre adecuado")
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

                # Extraer número de proceso (radicado) - el enlace con HypRadicado
                radicado_link = parent_container.find('a', id=re.compile(r'.*HypRadicado.*'))
                if radicado_link:
                    doc_info['numero_proceso'] = radicado_link.text.strip()
                    self.logger.debug(f"Número de proceso encontrado: {doc_info['numero_proceso']}")

                # Extraer otros campos usando IDs parciales
                # Interno
                interno_span = parent_container.find('span', id=re.compile(r'.*LblInterno.*'))
                if interno_span:
                    doc_info['interno'] = interno_span.text.strip()

                # Fecha proceso
                fecha_proc_span = parent_container.find('span', id=re.compile(r'.*LblFECHAPROC.*'))
                if fecha_proc_span:
                    doc_info['fecha_proceso'] = fecha_proc_span.text.strip()

                # Clase de proceso
                clase_span = parent_container.find('span', id=re.compile(r'.*LblClaseProceso.*'))
                if clase_span:
                    doc_info['clase_proceso'] = clase_span.text.strip()

                # Titular/Ponente
                ponente_span = parent_container.find('span', id=re.compile(r'.*LblPonente.*'))
                if ponente_span:
                    doc_info['titular'] = ponente_span.text.strip()

                # Sala de decisión
                sala_span = parent_container.find('span',
                                                  id=re.compile(r'.*LbNombreSalaDecision.*|.*LblNombreSalaDecision.*'))
                if sala_span:
                    doc_info['sala_decision'] = sala_span.text.strip()

                # Actor
                actor_span = parent_container.find('span', id=re.compile(r'.*LblActor.*'))
                if actor_span:
                    doc_info['actor'] = actor_span.text.strip()

                # Demandado
                demandado_span = parent_container.find('span', id=re.compile(r'.*LblDemandado.*'))
                if demandado_span:
                    doc_info['demandado'] = demandado_span.text.strip()

                # Fecha de providencia
                fecha_prov_span = parent_container.find('span', id=re.compile(r'.*Label1.*'))
                if fecha_prov_span:
                    doc_info['fecha_providencia'] = fecha_prov_span.text.strip()

                # Tipo de providencia
                tipo_prov_span = parent_container.find('span', id=re.compile(r'.*LblTIPOPROVIDENCIA.*'))
                if tipo_prov_span:
                    doc_info['tipo_providencia'] = tipo_prov_span.text.strip()

                # Agregar el documento
                documentos.append(doc_info)
                self.logger.debug(
                    f"Documento extraído: {doc_info.get('numero_proceso', 'Sin número')} - {doc_info.get('titular', 'Sin titular')}")

            except Exception as e:
                self.logger.error(f"Error procesando link {idx + 1}: {e}")
                continue

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