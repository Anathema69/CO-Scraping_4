# content_extractor.py
"""
Extractor de contenido mejorado basado en script_descarga_html.py
Especializado en extraer y estructurar contenido de documentos DIAN
"""

from bs4 import BeautifulSoup
import re
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ContentExtractor:
    """Extractor de contenido y metadatos de documentos DIAN"""

    def __init__(self):
        self.fecha_patterns = [
            r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',
            r'(\d{4})-(\d{2})-(\d{2})',
            r'(\d{1,2})/(\d{1,2})/(\d{4})',
            r'Bogotá,?\s+D\.?C\.?,?\s+(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})'
        ]

        self.meses_map = {
            'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
            'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
            'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'
        }

    def extract_metadata_and_content(self, html_content: str, url: str = None) -> Dict:
        """
        Extrae metadatos y contenido estructurado del HTML
        Basado en la lógica de script_descarga_html.py
        """
        soup = BeautifulSoup(html_content, 'html.parser')

        # Eliminar scripts y estilos para limpiar el contenido
        for script in soup(["script", "style"]):
            script.decompose()

        # Estructura de datos a extraer
        data = {
            'numero_oficio': '',
            'fecha': '',
            'tipo': 'Oficio',
            'tema': '',
            'descriptor': '',
            'ref': '',
            'content_sections': [],
            'tables': [],
            'firma': '',
            'url_fuente': url or '',
            'metadata_extracted': False,
            'content_raw': '',
            'content_clean': ''
        }

        # Obtener todo el texto limpio
        text_content = soup.get_text()
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]

        # Guardar contenido raw para procesamiento adicional
        data['content_raw'] = '\n'.join(lines)

        # Extraer número de oficio/concepto
        data['numero_oficio'] = self._extract_document_number(lines)

        # Extraer fecha
        data['fecha'] = self._extract_date(lines)

        # Extraer referencia
        data['ref'] = self._extract_reference(lines)

        # Extraer tema y descriptores
        self._extract_tema_descriptor(lines, data)

        # Extraer contenido principal
        data['content_sections'] = self._extract_content_sections(lines)

        # Extraer tablas si existen
        data['tables'] = self._extract_tables(soup)

        # Extraer firma
        data['firma'] = self._extract_signature(lines)

        # Determinar tipo de documento
        data['tipo'] = self._determine_document_type(text_content)

        # Generar contenido limpio para búsqueda
        data['content_clean'] = self._generate_clean_content(data)

        # Marcar si se extrajo metadata exitosamente
        data['metadata_extracted'] = bool(data['numero_oficio'] or data['fecha'])

        return data

    def _extract_document_number(self, lines: List[str]) -> str:
        """Extraer número de oficio o concepto"""
        patterns = [
            r'(?:Oficio|OFICIO|Concepto|CONCEPTO)\s*[Nn]?°?\s*(\d+(?:[-/]\d+)*)',
            r'No\.?\s*(\d+(?:[-/]\d+)*)',
            r'Radicado\s*[Nn]?°?\s*(\d+(?:[-/]\d+)*)',
            r'^\s*(\d{4,})\s*$'  # Número solo en una línea
        ]

        for line in lines[:20]:  # Buscar en las primeras líneas
            for pattern in patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    numero = match.group(1)
                    # Validar que sea un número válido
                    if len(numero) >= 3 and numero[0] != '0':
                        return numero

        return ''

    def _extract_date(self, lines: List[str]) -> str:
        """Extraer fecha del documento"""
        for line in lines[:30]:  # Buscar en las primeras líneas
            for pattern in self.fecha_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    if 'Bogotá' in pattern:
                        return match.group(1)
                    elif 'de' in line:  # Formato con mes en texto
                        dia = match.group(1)
                        mes_texto = match.group(2).lower()
                        año = match.group(3)

                        # Convertir mes a número
                        mes = self.meses_map.get(mes_texto, '')
                        if mes:
                            return f"{año}-{mes}-{dia.zfill(2)}"
                        else:
                            return match.group(0)
                    else:
                        # Formatos numéricos
                        grupos = match.groups()
                        if '/' in line:
                            return f"{grupos[2]}-{grupos[1].zfill(2)}-{grupos[0].zfill(2)}"
                        else:
                            return f"{grupos[0]}-{grupos[1].zfill(2)}-{grupos[2].zfill(2)}"

        return ''

    def _extract_reference(self, lines: List[str]) -> str:
        """Extraer referencia del documento"""
        ref_lines = []
        capturing = False

        for i, line in enumerate(lines):
            if re.match(r'^Ref\.?:?\s*', line, re.IGNORECASE):
                ref_lines.append(line)
                capturing = True
            elif capturing:
                # Continuar capturando líneas que parecen parte de la referencia
                if (not re.match(r'^[A-Z][a-z]+:', line) and
                        not re.match(r'^Señor|^Doctor|^Estimado', line, re.IGNORECASE) and
                        len(line) > 10):
                    ref_lines.append(line)
                else:
                    break

        return ' '.join(ref_lines)

    def _extract_tema_descriptor(self, lines: List[str], data: Dict):
        """Extraer tema y descriptor del documento"""
        # Buscar líneas con patrones de tema/descriptor
        for line in lines:
            # Buscar tema
            tema_match = re.search(r'Tema\s*:\s*(.+?)(?:Descriptor|Subtema|$)', line, re.IGNORECASE)
            if tema_match and not data['tema']:
                data['tema'] = tema_match.group(1).strip()

            # Buscar descriptor
            desc_match = re.search(r'Descriptor(?:es)?\s*:\s*(.+?)(?:Subtema|$)', line, re.IGNORECASE)
            if desc_match and not data['descriptor']:
                data['descriptor'] = desc_match.group(1).strip()

            # Buscar términos clave de impuestos
            if not data['tema']:
                if any(term in line.upper() for term in ['IVA', 'RENTA', 'RETENCION', 'IMPUESTO']):
                    for term in ['IVA', 'RENTA', 'RETENCION', 'IMPUESTO']:
                        if term in line.upper():
                            data['tema'] = term
                            break

    def _extract_content_sections(self, lines: List[str]) -> List[str]:
        """Extraer secciones de contenido principal"""
        content_sections = []
        current_section = []
        in_body = False
        start_patterns = ['Señor', 'Señora', 'Doctor', 'Doctora', 'Estimado', 'Respetado']
        end_patterns = ['Atentamente', 'Cordialmente', 'Director', 'Subdirector', 'Jefe', 'Coordinador']

        for i, line in enumerate(lines):
            # Detectar inicio del cuerpo
            if not in_body:
                if any(line.startswith(pattern) for pattern in start_patterns):
                    in_body = True
                elif i > 10 and re.search(r'solicitud|consulta|respuesta', line, re.IGNORECASE):
                    in_body = True

            if in_body:
                # Detectar fin del cuerpo (firma)
                if any(pattern in line for pattern in end_patterns):
                    if current_section:
                        content_sections.append(' '.join(current_section))
                    break

                # Agrupar en párrafos
                if line and len(line) > 20:
                    current_section.append(line)
                elif current_section:
                    content_sections.append(' '.join(current_section))
                    current_section = []

        # Agregar último párrafo si existe
        if current_section:
            content_sections.append(' '.join(current_section))

        # Si no se encontró contenido estructurado, usar enfoque alternativo
        if not content_sections:
            content_sections = self._extract_content_fallback(lines)

        return content_sections

    def _extract_content_fallback(self, lines: List[str]) -> List[str]:
        """Método alternativo para extraer contenido cuando no se encuentra estructura clara"""
        content_sections = []
        current_paragraph = []

        # Saltar encabezados obvios
        start_index = 0
        for i, line in enumerate(lines):
            if len(line) > 50 and not re.match(r'^(Oficio|Concepto|No\.|Ref\.)', line, re.IGNORECASE):
                start_index = i
                break

        # Agrupar líneas en párrafos
        for line in lines[start_index:]:
            # Ignorar líneas muy cortas o que parecen metadatos
            if len(line) < 20 or re.match(r'^(Página|Page|\d+$)', line, re.IGNORECASE):
                if current_paragraph:
                    content_sections.append(' '.join(current_paragraph))
                    current_paragraph = []
                continue

            # Agregar línea al párrafo actual
            current_paragraph.append(line)

            # Detectar fin de párrafo (punto final seguido de mayúscula)
            if line.endswith('.'):
                content_sections.append(' '.join(current_paragraph))
                current_paragraph = []

        # Agregar último párrafo
        if current_paragraph:
            content_sections.append(' '.join(current_paragraph))

        # Filtrar párrafos muy cortos
        content_sections = [p for p in content_sections if len(p) > 50]

        return content_sections

    def _extract_tables(self, soup: BeautifulSoup) -> List[List[List[str]]]:
        """Extraer tablas del documento"""
        tables_data = []

        for table in soup.find_all('table'):
            table_rows = []
            rows = table.find_all('tr')

            for row in rows:
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_data = [cell.get_text(strip=True) for cell in cells]
                    # Solo agregar filas con contenido
                    if any(cell for cell in row_data):
                        table_rows.append(row_data)

            if table_rows:
                tables_data.append(table_rows)

        return tables_data

    def _extract_signature(self, lines: List[str]) -> str:
        """Extraer firma del documento"""
        signature_keywords = [
            'Atentamente', 'Cordialmente', 'Sinceramente',
            'Director', 'Subdirector', 'Jefe', 'Coordinador',
            'Gerente', 'Administrador', 'Funcionario'
        ]

        # Buscar desde el final hacia atrás
        for i in range(len(lines) - 1, max(len(lines) - 20, 0), -1):
            line = lines[i]
            if any(keyword in line for keyword in signature_keywords):
                # Capturar esta línea y las siguientes (hasta 5 líneas)
                signature_lines = []
                for j in range(i, min(i + 5, len(lines))):
                    if lines[j]:
                        signature_lines.append(lines[j])

                return '\n'.join(signature_lines)

        return ''

    def _determine_document_type(self, text_content: str) -> str:
        """Determinar el tipo de documento (Oficio, Concepto, etc.)"""
        text_lower = text_content.lower()

        if 'concepto' in text_lower[:500]:
            return 'Concepto'
        elif 'oficio' in text_lower[:500]:
            return 'Oficio'
        elif 'resolución' in text_lower[:500]:
            return 'Resolución'
        elif 'circular' in text_lower[:500]:
            return 'Circular'
        else:
            return 'Documento'

    def _generate_clean_content(self, data: Dict) -> str:
        """Generar contenido limpio para búsqueda y análisis"""
        parts = []

        # Agregar metadatos
        if data['numero_oficio']:
            parts.append(f"Número: {data['numero_oficio']}")
        if data['fecha']:
            parts.append(f"Fecha: {data['fecha']}")
        if data['tema']:
            parts.append(f"Tema: {data['tema']}")
        if data['descriptor']:
            parts.append(f"Descriptor: {data['descriptor']}")
        if data['ref']:
            parts.append(f"Referencia: {data['ref']}")

        # Agregar contenido principal
        parts.extend(data['content_sections'])

        # Agregar firma si existe
        if data['firma']:
            parts.append(data['firma'])

        return '\n\n'.join(parts)

    def extract_summary(self, data: Dict) -> Dict:
        """Extraer un resumen del documento"""
        summary = {
            'numero': data.get('numero_oficio', ''),
            'fecha': data.get('fecha', ''),
            'tipo': data.get('tipo', ''),
            'tema': data.get('tema', ''),
            'descriptor': data.get('descriptor', ''),
            'contenido_extraido': bool(data.get('content_sections')),
            'num_parrafos': len(data.get('content_sections', [])),
            'num_tablas': len(data.get('tables', [])),
            'tiene_firma': bool(data.get('firma'))
        }

        # Agregar primer párrafo como preview
        if data.get('content_sections'):
            preview = data['content_sections'][0]
            if len(preview) > 200:
                preview = preview[:200] + '...'
            summary['preview'] = preview

        return summary