# scraper_dian_legacy_improved.py
"""
Scraper mejorado para documentos DIAN legacy (2001-2009)
Combina navegación de scraper_legacy con extracción mejorada de script_descarga_html
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
import time
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging
import json
from pathlib import Path

from .content_extractor import ContentExtractor
from .html_formatter import HTMLFormatter
from .encoding_fixer import EncodingFixer

logger = logging.getLogger(__name__)


class DIANLegacyImprovedScraper:
    """Scraper mejorado para documentos DIAN de años 2001-2009"""

    def __init__(self, progress_callback=None):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.session.headers.update(self.headers)

        # Inicializar helpers
        self.content_extractor = ContentExtractor()
        self.html_formatter = HTMLFormatter()
        self.encoding_fixer = EncodingFixer()

        # Tracking de progreso
        self.progress_callback = progress_callback
        self.stats = {
            'expected': 0,
            'processed': 0,
            'downloaded': 0,
            'errors': 0,
            'total_size': 0,
            'current_action': 'Iniciando...',
            'documents': []
        }

        # Mapeo de nombres de meses
        self.meses = {
            1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
            5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
            9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
        }

    def update_progress(self, **kwargs):
        """Actualizar estadísticas de progreso"""
        self.stats.update(kwargs)
        if self.progress_callback:
            stats_copy = self.stats.copy()
            if 'documents' in stats_copy:
                clean_docs = []
                for doc in stats_copy['documents']:
                    if isinstance(doc, dict):
                        clean_doc = {k: v for k, v in doc.items()
                                     if k not in ['soup', 'content_html', 'full_content']}
                        clean_docs.append(clean_doc)
                stats_copy['documents'] = clean_docs
            self.progress_callback(stats_copy)

    def build_month_url(self, year: int, month: int) -> Tuple[str, str]:
        """Construir URLs para una página de mes específico"""
        year_suffix = str(year)[2:]
        month_name = self.meses[month]

        if year == 2001:
            url_primary = f"https://cijuf.org.co/codian01/{month_name}.htm"
            url_alt = f"https://cijuf.org.co/codian01/{month_name}.html"
        elif year <= 2004:
            # Años 2002-2004 usan .htm
            url_primary = f"https://cijuf.org.co/codian{year_suffix:0>2}/{month_name}i{year_suffix:0>2}.htm"
            url_alt = f"https://cijuf.org.co/codian{year_suffix:0>2}/{month_name}i{year_suffix:0>2}.html"
        else:
            # Años 2005-2009 usan .html
            url_primary = f"https://cijuf.org.co/codian{year_suffix:0>2}/{month_name}i{year_suffix:0>2}.html"
            url_alt = f"https://cijuf.org.co/codian{year_suffix:0>2}/{month_name}i{year_suffix:0>2}.htm"

        return url_primary, url_alt

    def fetch_page(self, url_primary: str, url_alt: str = None) -> Optional[str]:
        """Obtener página con manejo mejorado de encoding"""
        urls_to_try = [url_primary]
        if url_alt:
            urls_to_try.append(url_alt)

        for url in urls_to_try:
            try:
                logger.info(f"Intentando obtener: {url}")
                response = self.session.get(url, timeout=30)

                if response.status_code == 200:
                    # Usar el encoding_fixer para detectar y decodificar correctamente
                    content = self.encoding_fixer.detect_and_decode(response.content)

                    # Aplicar correcciones de mojibake
                    content = self.encoding_fixer.fix_mojibake(content)

                    return content

            except Exception as e:
                logger.warning(f"Error obteniendo {url}: {e}")
                continue

        return None

    def extract_documents_from_month_page(self, html_content: str, year: int, month: int) -> List[Dict]:
        """Extraer información de documentos desde página de mes"""
        documents = []
        seen_numbers = set()

        # ESTRATEGIA PRINCIPAL: Buscar referencias a archivos en el texto/HTML
        # Basado en el análisis, el método text_reference es el más efectivo

        # 1. Buscar todas las referencias a archivos .htm en el contenido completo
        file_pattern = r'\b([co])(\d{3,5})\.html?\b'  # Acepta tanto .htm como .html
        file_matches = re.findall(file_pattern, html_content, re.IGNORECASE)

        for tipo_letra, numero in file_matches:
            # Validar que el número tenga longitud correcta (típicamente 5 dígitos)
            if len(numero) >= 3 and numero not in seen_numbers:
                seen_numbers.add(numero)


                # Construir información del documento con extensión correcta según el año
                if year <= 2004:
                    filename = f"{tipo_letra.lower()}{numero}.htm"
                else:
                    filename = f"{tipo_letra.lower()}{numero}.html"
                doc_url = self._build_document_url(filename, year, month)

                doc_info = {
                    'numero': numero,
                    'fecha': f"{year}-{month:02d}-01",  # Fecha por defecto
                    'tema': '',
                    'descriptor': '',
                    'subtema': '',
                    'tipo': 'oficio' if tipo_letra.lower() == 'o' else 'concepto',
                    'year': year,
                    'month': month,
                    'detail_url': doc_url,
                    'filename': filename
                }

                documents.append(doc_info)

        # 2. Si hay documentos, intentar enriquecer con información adicional
        if documents:
            soup = BeautifulSoup(html_content, 'html.parser')

            # Buscar información adicional en tablas o texto cercano
            for doc in documents:
                # Buscar el número en el contexto para extraer más información
                numero = doc['numero']

                # Buscar en todo el texto patrones que contengan el número
                info_pattern = rf'\b{numero}\b[^<]*?(?:Tema|tema)[:\s]*([^<\n]+)'
                info_match = re.search(info_pattern, html_content, re.IGNORECASE)
                if info_match:
                    tema_text = info_match.group(1).strip()
                    # Limpiar y limitar longitud
                    tema_text = re.sub(r'\s+', ' ', tema_text)[:100]
                    doc['tema'] = self.encoding_fixer.fix_mojibake(tema_text)

                # Buscar fecha asociada al número
                fecha_pattern = rf'\b{numero}\b[^\n]*?(\d{{1,2}}[-/]\d{{1,2}}[-/]\d{{4}})'
                fecha_match = re.search(fecha_pattern, html_content)
                if fecha_match:
                    fecha_str = fecha_match.group(1)
                    # Parsear fecha
                    fecha_parts = re.match(r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', fecha_str)
                    if fecha_parts:
                        dia, mes_num, año = fecha_parts.groups()
                        doc['fecha'] = f"{año}-{mes_num:0>2}-{dia:0>2}"

        # 3. Si no encontramos documentos con el método principal, intentar métodos alternativos
        if not documents:
            logger.info(f"No se encontraron documentos con método text_reference, intentando métodos alternativos...")

            # Método alternativo 1: Buscar en enlaces HTML
            soup = BeautifulSoup(html_content, 'html.parser')

            for link in soup.find_all('a', href=True):
                href = link.get('href', '')

                if re.match(r'^[co]\d+\.htm', href.lower()):
                    numero_match = re.search(r'[co](\d+)\.htm', href.lower())
                    if numero_match:
                        numero = numero_match.group(1)

                        if numero not in seen_numbers:
                            seen_numbers.add(numero)

                            doc_url = self._build_document_url(href, year, month)

                            doc_info = {
                                'numero': numero,
                                'fecha': f"{year}-{month:02d}-01",
                                'tema': '',
                                'descriptor': '',
                                'subtema': '',
                                'tipo': 'oficio' if href.startswith('o') else 'concepto',
                                'year': year,
                                'month': month,
                                'detail_url': doc_url,
                                'filename': href
                            }

                            documents.append(doc_info)

            # Método alternativo 2: Buscar patrones de números con fechas
            if not documents:
                documents = self._extract_documents_by_pattern_alternative(html_content, year, month)

        logger.info(f"Encontrados {len(documents)} documentos en {year}/{month:0>2}")

        if documents:
            logger.debug(f"Métodos usados: text_reference. Ejemplo: {documents[0]}")
            logger.debug(f"Primeros 5 números: {[d['numero'] for d in documents[:5]]}")

        return documents

    def _build_document_url(self, href: str, year: int, month: int) -> str:
        """Construir URL completa del documento"""
        year_suffix = str(year)[2:]
        month_name = self.meses[month]

        # Para todos los años (2001-2009), la estructura es:
        # https://cijuf.org.co/codianXX/mes/archivo.htm(l)
        if year == 2001:
            base_url = f"https://cijuf.org.co/codian01/{month_name}"
        else:
            base_url = f"https://cijuf.org.co/codian{year_suffix:0>2}/{month_name}"

        return f"{base_url}/{href}"

    def _extract_document_info_from_link(self, link_element, year: int, month: int) -> Optional[Dict]:
        """Extraer información de un enlace usando lógica mejorada"""
        href = link_element.get('href', '')
        link_text = link_element.get_text(strip=True)

        # Extraer número del href si es un enlace directo a documento
        numero = ''
        if re.match(r'^[co]\d+\.htm', href.lower()):
            # Extraer número del nombre del archivo (c69618.htm -> 69618)
            numero_match = re.search(r'[co](\d+)\.htm', href.lower())
            if numero_match:
                numero = numero_match.group(1)
        else:
            # Si no es un enlace directo, buscar número en el texto
            numero_match = re.search(r'(\d+)', link_text)
            if numero_match:
                numero = numero_match.group(1)

        if not numero:
            return None

        doc_info = {
            'numero': numero,
            'fecha': '',
            'tema': '',
            'descriptor': '',
            'subtema': '',
            'tipo': 'oficio' if href.startswith('o') else 'concepto',
            'year': year,
            'month': month
        }

        # Buscar información en el contexto cercano
        parent_tr = link_element.find_parent('tr')
        if parent_tr:
            row_text = parent_tr.get_text(' ', strip=True)

            # Aplicar correcciones de encoding al texto de la fila
            row_text = self.encoding_fixer.fix_mojibake(row_text)

            # Extraer fecha
            fecha_patterns = [
                r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
                r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',
                r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})'
            ]

            for pattern in fecha_patterns:
                fecha_match = re.search(pattern, row_text)
                if fecha_match:
                    if 'de' in pattern:
                        # Formato con mes en texto
                        dia = fecha_match.group(1)
                        mes_texto = fecha_match.group(2).lower()
                        año = fecha_match.group(3)
                        # Convertir mes texto a número
                        mes_num = month  # usar mes actual como fallback
                        for num, nombre in self.meses.items():
                            if nombre in mes_texto:
                                mes_num = num
                                break
                        doc_info['fecha'] = f"{año}-{mes_num:0>2}-{dia:0>2}"
                    else:
                        # Formato numérico
                        grupos = fecha_match.groups()
                        if len(grupos[0]) == 4:  # año primero
                            doc_info['fecha'] = f"{grupos[0]}-{grupos[1]:0>2}-{grupos[2]:0>2}"
                        else:  # día primero
                            doc_info['fecha'] = f"{grupos[2]}-{grupos[1]:0>2}-{grupos[0]:0>2}"
                    break

            # Extraer tema, descriptor y subtema
            doc_info['tema'] = self._extract_field(row_text, 'Tema')
            doc_info['descriptor'] = self._extract_field(row_text, 'Descriptor')
            doc_info['subtema'] = self._extract_field(row_text, 'Subtema')

        return doc_info

    def _extract_field(self, text: str, field_name: str) -> str:
        """Extraer un campo específico del texto"""
        pattern = rf'{field_name}(?:es)?\s*:\s*([^:]+?)(?:Tema|Descriptor|Subtema|\[|$)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ''

    def _extract_documents_from_tables(self, soup, year: int, month: int) -> List[Dict]:
        """Extraer documentos de tablas HTML"""
        documents = []

        for table in soup.find_all('table'):
            rows = table.find_all('tr')

            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue

                # Buscar enlace primero para obtener el número correcto
                link = row.find('a', href=re.compile(r'^[co]\d+\.htm', re.IGNORECASE))
                numero = ''
                detail_url = ''

                if link:
                    href = link.get('href', '')
                    # Extraer número del href (c69618.htm -> 69618)
                    numero_match = re.search(r'[co](\d+)\.htm', href.lower())
                    if numero_match:
                        numero = numero_match.group(1)
                        detail_url = self._build_document_url(href, year, month)

                # Si no encontramos número en el enlace, buscar en el texto
                if not numero:
                    row_text = ' '.join([cell.get_text(strip=True) for cell in cells])
                    row_text = self.encoding_fixer.fix_mojibake(row_text)

                    # Buscar número en el texto
                    numero_match = re.search(r'(?:No\.?\s*|Concepto\s+No\.?\s*|Oficio\s+No\.?\s*)(\d+)',
                                             row_text, re.IGNORECASE)
                    if numero_match:
                        # Verificar si el número parece ser demasiado largo (problema de concatenación)
                        numero_found = numero_match.group(1)
                        if len(numero_found) > 6:  # Los números típicos son de 5 dígitos
                            # Tomar solo los primeros 5 dígitos
                            numero = numero_found[:5]
                        else:
                            numero = numero_found

                if not numero:
                    continue

                # Concatenar texto de todas las celdas para extraer información
                row_text = ' '.join([cell.get_text(strip=True) for cell in cells])
                row_text = self.encoding_fixer.fix_mojibake(row_text)

                doc_info = {
                    'numero': numero,
                    'fecha': '',
                    'tema': self._extract_field(row_text, 'Tema'),
                    'descriptor': self._extract_field(row_text, 'Descriptor'),
                    'subtema': self._extract_field(row_text, 'Subtema'),
                    'tipo': 'oficio' if 'oficio' in row_text.lower() else 'concepto',
                    'year': year,
                    'month': month,
                    'detail_url': detail_url
                }

                # Buscar fecha
                fecha_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', row_text)
                if fecha_match:
                    dia, mes, año = fecha_match.groups()
                    doc_info['fecha'] = f"{año}-{mes:0>2}-{dia:0>2}"

                documents.append(doc_info)

        return documents

    def _extract_documents_by_pattern_alternative(self, html_content: str, year: int, month: int) -> List[Dict]:
        """Método alternativo para extraer documentos cuando los métodos principales fallan"""
        documents = []
        seen_numbers = set()

        # Limpiar el contenido
        html_content = self.encoding_fixer.fix_mojibake(html_content)

        # Intentar varios patrones
        patterns = [
            # Números con fechas concatenadas (06961831-07-2001)
            (r'(\d{7,10})[-/](\d{2})[-/](\d{4})', 'concatenated'),
            # Números entre corchetes
            (r'\[(\d{5,6})\]', 'bracketed'),
            # Concepto No. #####
            (r'(?:Concepto|Oficio)\s+No\.?\s*(\d{5,6})', 'concept_number'),
            # Números de 5 dígitos sueltos
            (r'\b(\d{5})\b(?![-/])', 'standalone'),
        ]

        for pattern, method_name in patterns:
            matches = re.findall(pattern, html_content)

            for match in matches:
                numero = None
                fecha = f"{year}-{month:02d}-01"

                if method_name == 'concatenated' and len(match) == 3:
                    # Extraer número de la concatenación
                    numero_largo = match[0]
                    if len(numero_largo) >= 7:
                        numero = numero_largo[:5]
                    else:
                        numero = numero_largo
                    # Intentar extraer fecha
                    try:
                        fecha = f"{match[2]}-{month:02d}-{match[1]}"
                    except:
                        pass
                else:
                    # Para otros patrones, el número es el primer grupo
                    numero = match[0] if isinstance(match, tuple) else match

                # Validar número
                if numero and numero.isdigit() and len(numero) >= 3 and len(numero) <= 6:
                    if numero not in seen_numbers:
                        seen_numbers.add(numero)


                        # Asumir que es concepto por defecto con extensión correcta
                        if year <= 2004:
                            filename = f"c{numero}.htm"
                        else:
                            filename = f"c{numero}.html"
                        doc_url = self._build_document_url(filename, year, month)

                        documents.append({
                            'numero': numero,
                            'fecha': fecha,
                            'tema': '',
                            'descriptor': '',
                            'subtema': '',
                            'tipo': 'concepto',
                            'year': year,
                            'month': month,
                            'detail_url': doc_url,
                            'filename': filename,
                            'extraction_method': method_name
                        })

        return documents

    def download_and_process_document(self, doc_url: str) -> Optional[Dict]:
        """Descargar y procesar un documento individual usando la lógica mejorada"""
        try:
            logger.info(f"Descargando documento: {doc_url}")
            response = self.session.get(doc_url, timeout=30)

            if response.status_code != 200:
                logger.warning(f"Error HTTP {response.status_code} para {doc_url}")
                return None

            # Decodificar correctamente
            content = self.encoding_fixer.detect_and_decode(response.content)
            content = self.encoding_fixer.fix_mojibake(content)

            # Extraer metadatos y contenido usando el extractor mejorado
            metadata = self.content_extractor.extract_metadata_and_content(content, doc_url)

            return metadata

        except Exception as e:
            logger.error(f"Error descargando {doc_url}: {e}")
            return None

    def scrape_month(self, year: int, month: int) -> List[Dict]:
        """Scrape de todos los documentos de un mes específico"""
        self.update_progress(
            current_action=f"Procesando {self.meses[month]} de {year}..."
        )

        # Obtener página del mes
        url_primary, url_alt = self.build_month_url(year, month)
        html_content = self.fetch_page(url_primary, url_alt)

        if not html_content:
            logger.warning(f"No se pudo obtener contenido para {year}/{month:0>2}")
            self.update_progress(errors=self.stats['errors'] + 1)
            return []

        # Extraer lista de documentos
        documents = self.extract_documents_from_month_page(html_content, year, month)

        self.update_progress(
            processed=self.stats['processed'] + len(documents),
            current_action=f"Procesados {len(documents)} documentos de {self.meses[month]} {year}"
        )

        return documents

    def scrape_year(self, year: int, months: List[int] = None) -> Dict[int, List[Dict]]:
        """Scrape de todos los meses de un año"""
        if months is None:
            months = list(range(1, 13))

        results = {}

        self.update_progress(
            expected=len(months) * 50,
            current_action=f"Iniciando procesamiento del año {year}..."
        )

        for month in months:
            try:
                documents = self.scrape_month(year, month)
                if documents:
                    results[month] = documents
                time.sleep(1)  # Pausa entre requests
            except Exception as e:
                logger.error(f"Error procesando {year}/{month:0>2}: {e}")
                self.update_progress(errors=self.stats['errors'] + 1)

        return results

    def save_documents(self, documents: List[Dict], base_folder: str, year: int, month: int,
                       download_full_content: bool = True, max_documents: int = None):
        """Guardar documentos con contenido completo y formato mejorado"""
        # Crear estructura de carpetas
        year_folder = os.path.join(base_folder, str(year))
        month_folder = os.path.join(year_folder, f"{month:0>2}")

        # Limitar documentos si se especifica
        if max_documents:
            documents = documents[:max_documents]

        saved_documents = []

        for i, doc in enumerate(documents, 1):
            try:
                self.update_progress(
                    current_action=f"Procesando documento {i}/{len(documents)}: {doc.get('numero', 'Sin número')}"
                )

                # Descargar contenido completo si está disponible y se solicita
                if download_full_content and doc.get('detail_url'):
                    logger.info(f"Descargando contenido de: {doc['detail_url']}")
                    metadata = self.download_and_process_document(doc['detail_url'])
                    if metadata:
                        # Combinar información existente con la extraída
                        # Preservar el número original y otros datos básicos
                        original_numero = doc['numero']
                        original_tipo = doc['tipo']
                        original_url = doc['detail_url']

                        doc.update(metadata)

                        # Restaurar datos originales si fueron sobrescritos
                        doc['numero'] = original_numero
                        doc['tipo'] = original_tipo
                        doc['detail_url'] = original_url
                        doc['numero_oficio'] = original_numero  # Para el formateador HTML
                        doc['content_downloaded'] = True

                        logger.info(f"Contenido extraído exitosamente para documento {original_numero}")
                    else:
                        doc['content_downloaded'] = False
                        doc['numero_oficio'] = doc['numero']  # Asegurar que existe para el HTML
                        logger.warning(f"No se pudo extraer contenido para documento {doc['numero']}")
                else:
                    doc['numero_oficio'] = doc['numero']  # Asegurar que existe para el HTML

                # Determinar carpeta por tema
                tema = doc.get('tema', '').strip() or "SIN_CLASIFICAR"
                tema_folder = self._clean_folder_name(tema)

                doc_folder = os.path.join(month_folder, tema_folder)
                os.makedirs(doc_folder, exist_ok=True)

                # Generar nombre de archivo
                filename = self._format_document_filename(doc, year, month)
                filepath = os.path.join(doc_folder, filename)

                # Generar HTML formateado
                formatted_html = self.html_formatter.generate_formatted_html(doc)

                # Guardar archivo
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(formatted_html)

                logger.info(f"Guardado: {filepath}")

                # Guardar información para resumen
                saved_documents.append({
                    'numero': doc.get('numero'),
                    'tipo': doc.get('tipo'),
                    'fecha': doc.get('fecha'),
                    'tema': doc.get('tema'),
                    'archivo': filepath,
                    'content_downloaded': doc.get('content_downloaded', False)
                })

                self.update_progress(
                    downloaded=self.stats['downloaded'] + 1,
                    current_action=f"Guardado: {doc.get('numero', 'Sin número')}"
                )

                # Pausa para no sobrecargar el servidor
                if download_full_content and i < len(documents):
                    time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error guardando documento {doc.get('numero')}: {e}", exc_info=True)
                self.update_progress(errors=self.stats['errors'] + 1)

        # Guardar resumen JSON
        self._save_summary(saved_documents, base_folder, year, month)

        return saved_documents

    def _save_summary(self, documents: List[Dict], base_folder: str, year: int, month: int):
        """Guardar resumen JSON de los documentos procesados"""
        summary_file = os.path.join(base_folder, str(year), f"{month:0>2}", "resumen.json")
        os.makedirs(os.path.dirname(summary_file), exist_ok=True)

        summary = {
            'year': year,
            'month': month,
            'mes_nombre': self.meses[month],
            'total_documents': len(documents),
            'documents_with_content': sum(1 for d in documents if d.get('content_downloaded')),
            'fecha_procesamiento': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'documents': documents
        }

        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Resumen guardado en: {summary_file}")

    def _clean_folder_name(self, name: str) -> str:
        """Limpiar nombre para uso como carpeta"""
        name = name.upper()

        # Reemplazar caracteres problemáticos
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\n', '\r', '\t']
        for char in invalid_chars:
            name = name.replace(char, '_')

        # Normalizar espacios
        name = re.sub(r'\s+', '_', name)
        name = re.sub(r'_+', '_', name)
        name = name.strip('_.')

        # Limitar longitud
        if len(name) > 100:
            name = name[:100]

        return name or "SIN_CLASIFICAR"

    def _format_document_filename(self, doc: Dict, year: int, month: int) -> str:
        """Generar nombre de archivo para el documento"""
        tipo = "Concepto" if doc.get('tipo') == 'concepto' else 'Oficio'
        numero = doc.get('numero', 'SN')

        # Formatear fecha
        fecha_str = doc.get('fecha', '')
        if fecha_str:
            try:
                fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d")
                fecha_formateada = fecha_obj.strftime("%d-%m-%Y")
            except:
                fecha_formateada = f"01-{month:0>2}-{year}"
        else:
            fecha_formateada = f"01-{month:0>2}-{year}"

        filename = f"DIAN_{tipo}_{numero}_de_{fecha_formateada}.html"

        # Limpiar caracteres no válidos
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

        return filename

    def batch_process_urls(self, urls: List[str], output_folder: str = "./batch_output"):
        """Procesar una lista de URLs específicas de documentos"""
        os.makedirs(output_folder, exist_ok=True)
        results = []

        for i, url in enumerate(urls, 1):
            try:
                self.update_progress(
                    current_action=f"Procesando URL {i}/{len(urls)}"
                )

                # Descargar y procesar
                metadata = self.download_and_process_document(url)

                if metadata:
                    # Generar HTML formateado
                    formatted_html = self.html_formatter.generate_formatted_html(metadata)

                    # Generar nombre de archivo
                    numero = metadata.get('numero_oficio', 'sin_numero')
                    filename = f"DIAN_Documento_{numero}.html"
                    filepath = os.path.join(output_folder, filename)

                    # Guardar
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(formatted_html)

                    results.append({
                        'url': url,
                        'status': 'success',
                        'file': filepath
                    })
                else:
                    results.append({
                        'url': url,
                        'status': 'error',
                        'error': 'No se pudo procesar el documento'
                    })

                time.sleep(0.5)  # Pausa entre requests

            except Exception as e:
                logger.error(f"Error procesando {url}: {e}")
                results.append({
                    'url': url,
                    'status': 'error',
                    'error': str(e)
                })

        # Guardar resumen
        summary_file = os.path.join(output_folder, 'batch_resumen.json')
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return results