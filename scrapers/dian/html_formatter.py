# html_formatter.py
"""
Formateador HTML para generar documentos con estilo profesional DIAN
Basado en script_descarga_html.py con mejoras adicionales
"""

from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, List, Optional
import re
import logging

logger = logging.getLogger(__name__)


class HTMLFormatter:
    """Generador de HTML formateado con estilo DIAN"""

    def __init__(self):
        self.css_styles = self._get_css_styles()

    def _get_css_styles(self) -> str:
        """Retorna los estilos CSS para el documento"""
        return """
        body {
            font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
            margin: 40px;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #1e3a5f;
            border-bottom: 3px solid #ff6b00;
            padding-bottom: 15px;
            margin-bottom: 30px;
            font-size: 28px;
        }
        h2 {
            color: #2c3e50;
            margin-top: 25px;
            font-size: 22px;
        }
        h3 {
            color: #34495e;
            margin-top: 20px;
            font-size: 18px;
        }
        .header-info {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .logo-text {
            font-weight: bold;
            color: #1e3a5f;
        }
        .doc-number {
            color: #ff6b00;
            font-weight: bold;
            font-size: 20px;
        }
        .metadata {
            background: #f8f9fa;
            padding: 20px;
            margin: 20px 0;
            border-left: 4px solid #3498db;
            border-radius: 5px;
        }
        .metadata p {
            margin: 10px 0;
        }
        .metadata strong {
            color: #2c3e50;
            min-width: 140px;
            display: inline-block;
        }
        .reference {
            background: #e8f4f8;
            padding: 15px;
            margin: 20px 0;
            border-left: 3px solid #17a2b8;
            font-style: italic;
            border-radius: 5px;
        }
        .content {
            margin-top: 30px;
            padding: 20px;
            background: #fff;
            border: 1px solid #dee2e6;
            border-radius: 5px;
        }
        .content-section {
            margin-bottom: 20px;
            text-align: justify;
            line-height: 1.8;
        }
        .content-section p {
            margin-bottom: 15px;
        }
        .table-container {
            margin: 20px 0;
            overflow-x: auto;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        td, th {
            padding: 10px;
            border: 1px solid #ddd;
            text-align: left;
        }
        th {
            background: #f2f2f2;
            font-weight: bold;
            color: #2c3e50;
        }
        tr:nth-child(even) {
            background: #f9f9f9;
        }
        .firma-section {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #dee2e6;
            text-align: center;
            font-style: italic;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #dee2e6;
            color: #666;
            font-size: 0.9em;
            text-align: center;
        }
        .footer p {
            margin: 5px 0;
        }
        .warning {
            background: #fff3cd;
            padding: 15px;
            margin: 20px 0;
            border: 1px solid #ffc107;
            border-radius: 5px;
        }
        .warning strong {
            color: #856404;
        }
        .success {
            background: #d4edda;
            padding: 15px;
            margin: 20px 0;
            border: 1px solid #28a745;
            border-radius: 5px;
        }
        .success strong {
            color: #155724;
        }
        .badge {
            display: inline-block;
            padding: 3px 8px;
            background: #007bff;
            color: white;
            border-radius: 3px;
            font-size: 12px;
            margin-left: 10px;
        }
        .badge.concepto {
            background: #28a745;
        }
        .badge.oficio {
            background: #17a2b8;
        }
        .badge.resolucion {
            background: #ffc107;
            color: #333;
        }
        .original-content {
            margin-top: 20px;
            padding: 15px;
            background: #fafafa;
            border: 1px solid #e0e0e0;
            border-radius: 5px;
        }
        @media print {
            body {
                background: white;
            }
            .container {
                box-shadow: none;
                padding: 0;
            }
            .no-print {
                display: none;
            }
        }
        """

    def generate_formatted_html(self, metadata: Dict, include_original: bool = False) -> str:
        """
        Genera un HTML formateado con el estilo DIAN

        Args:
            metadata: Diccionario con los metadatos y contenido del documento
            include_original: Si incluir el contenido HTML original sin procesar

        Returns:
            HTML formateado como string
        """
        # Determinar si el contenido fue extraído exitosamente
        has_content = bool(metadata.get('content_sections'))

        # Formatear fecha
        fecha_display = self._format_date(metadata.get('fecha', ''))

        # Generar el descriptor
        descriptor = metadata.get('descriptor', '')
        if not descriptor and metadata.get('ref'):
            descriptor = self._extract_descriptor_from_ref(metadata['ref'])

        # Determinar el tipo de badge
        tipo = metadata.get('tipo', 'Documento')
        badge_class = tipo.lower().replace(' ', '')

        # Construir el HTML
        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DIAN - {tipo} {metadata.get('numero_oficio', 'Sin número')}</title>
    <style>
{self.css_styles}
    </style>
</head>
<body>
    <div class="container">
        <div class="header-info">
            <div class="logo-text">
                REPÚBLICA DE COLOMBIA<br>
                Ministerio de Hacienda y Crédito Público
            </div>
            <div class="doc-number">
                {tipo} N° {metadata.get('numero_oficio', 'Sin número')}
                <span class="badge {badge_class}">{tipo}</span>
            </div>
        </div>

        <h1>Dirección de Impuestos y Aduanas Nacionales - DIAN</h1>

        <div class="metadata">
            <p><strong>Fecha:</strong> {fecha_display}</p>
            <p><strong>Tipo de Documento:</strong> {tipo}</p>
            <p><strong>Tema:</strong> {metadata.get('tema', 'No especificado')}</p>
            {f'<p><strong>Descriptor:</strong> {descriptor}</p>' if descriptor else ''}
            {f'<p><strong>Subtema:</strong> {metadata.get("subtema")}</p>' if metadata.get('subtema') else ''}
            {f'<p><strong>URL Fuente:</strong> <a href="{metadata["url_fuente"]}" target="_blank">{self._shorten_url(metadata["url_fuente"])}</a></p>' if metadata.get('url_fuente') else ''}
        </div>
"""

        # Agregar contenido principal
        if has_content:
            html += self._format_content_section(metadata)
        else:
            html += self._format_no_content_warning(metadata)

        # Agregar contenido original si se solicita
        if include_original and metadata.get('content_raw'):
            html += self._format_original_content(metadata['content_raw'])

        # Agregar footer
        html += self._format_footer(metadata)

        html += """
    </div>
</body>
</html>"""

        return html

    def _format_date(self, fecha_str: str) -> str:
        """Formatea la fecha para mostrarla de manera legible"""
        if not fecha_str:
            return "No especificada"

        try:
            # Intentar parsear formato YYYY-MM-DD
            if re.match(r'\d{4}-\d{2}-\d{2}', fecha_str):
                fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d")
                meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                         'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
                return f"{fecha_obj.day} de {meses[fecha_obj.month - 1]} de {fecha_obj.year}"
            else:
                return fecha_str
        except:
            return fecha_str

    def _extract_descriptor_from_ref(self, ref: str) -> str:
        """Extrae un descriptor conciso de la referencia"""
        if not ref:
            return ""

        # Limpiar la referencia
        ref_clean = ref.replace('Ref.:', '').replace('Ref:', '').strip()

        # Si es muy larga, tomar solo la primera parte
        if len(ref_clean) > 150:
            # Buscar el primer punto o coma para cortar
            cut_point = ref_clean.find('.')
            if cut_point > 0 and cut_point < 150:
                ref_clean = ref_clean[:cut_point]
            else:
                ref_clean = ref_clean[:150] + '...'

        return ref_clean

    def _shorten_url(self, url: str) -> str:
        """Acorta una URL para mostrarla"""
        if not url:
            return ""

        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path

        # Extraer la parte más relevante del path
        path_parts = parsed.path.split('/')
        relevant_parts = [p for p in path_parts if p and not p.startswith('index')]

        if len(relevant_parts) > 2:
            return f"{domain}/.../{relevant_parts[-1]}"
        elif relevant_parts:
            return f"{domain}/{'/'.join(relevant_parts)}"
        else:
            return domain

    def _format_content_section(self, metadata: Dict) -> str:
        """Formatea la sección de contenido principal"""
        html = """
        <div class="content">
"""

        # Agregar mensaje de éxito si se extrajo contenido
        if metadata.get('metadata_extracted'):
            html += """
            <div class="success">
                <strong>✓ Contenido extraído exitosamente</strong>
                <p>Se han identificado {num_parrafos} secciones de contenido{num_tablas}.</p>
            </div>
""".format(
                num_parrafos=len(metadata.get('content_sections', [])),
                num_tablas=f" y {len(metadata.get('tables', []))} tabla(s)" if metadata.get('tables') else ""
            )

        # Agregar referencia si existe
        if metadata.get('ref'):
            html += f"""
            <div class="reference">
                <strong>Referencia:</strong> {metadata['ref']}
            </div>
"""

        # Agregar secciones de contenido
        for i, section in enumerate(metadata.get('content_sections', []), 1):
            if section:
                # Dividir secciones muy largas en párrafos
                paragraphs = self._split_into_paragraphs(section)
                html += f"""
            <div class="content-section">
"""
                for paragraph in paragraphs:
                    html += f"""                <p>{paragraph}</p>
"""
                html += """            </div>
"""

        # Agregar tablas si existen
        if metadata.get('tables'):
            html += self._format_tables(metadata['tables'])

        # Agregar firma si existe
        if metadata.get('firma'):
            html += f"""
            <div class="firma-section">
                <p>{metadata['firma'].replace(chr(10), '<br>')}</p>
            </div>
"""

        html += """
        </div>
"""
        return html

    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Divide un texto largo en párrafos más manejables"""
        # Si el texto ya tiene saltos de línea, usarlos
        if '\n' in text:
            paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        else:
            # Dividir por puntos seguidos de mayúscula
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)

            # Agrupar oraciones en párrafos de tamaño razonable
            paragraphs = []
            current = []
            current_length = 0

            for sentence in sentences:
                current.append(sentence)
                current_length += len(sentence)

                # Crear nuevo párrafo si es muy largo
                if current_length > 500:
                    paragraphs.append(' '.join(current))
                    current = []
                    current_length = 0

            if current:
                paragraphs.append(' '.join(current))

        return paragraphs

    def _format_tables(self, tables: List[List[List[str]]]) -> str:
        """Formatea las tablas del documento"""
        html = """
            <div class="table-container">
                <h3>Tablas y Datos Adicionales</h3>
"""

        for i, table in enumerate(tables, 1):
            if not table:
                continue

            html += f"""
                <h4>Tabla {i}</h4>
                <table>
"""

            for j, row in enumerate(table):
                if j == 0 and len(row) > 1:  # Primera fila como encabezados si tiene múltiples columnas
                    html += "                    <tr>\n"
                    for cell in row:
                        html += f"                        <th>{self._escape_html(cell)}</th>\n"
                    html += "                    </tr>\n"
                else:
                    html += "                    <tr>\n"
                    for cell in row:
                        html += f"                        <td>{self._escape_html(cell)}</td>\n"
                    html += "                    </tr>\n"

            html += """
                </table>
"""

        html += """
            </div>
"""
        return html

    def _format_no_content_warning(self, metadata: Dict) -> str:
        """Formatea advertencia cuando no se pudo extraer contenido"""
        html = """
        <div class="content">
            <div class="warning">
                <strong>⚠ Nota:</strong> El contenido completo de este documento no pudo ser recuperado automáticamente.
                <p>Este documento corresponde al sistema de conceptos y oficios de la DIAN.</p>
"""

        if metadata.get('url_fuente'):
            html += f"""
                <p>Puede intentar acceder directamente al documento original: 
                <a href="{metadata['url_fuente']}" target="_blank">{metadata['url_fuente']}</a></p>
"""

        # Si hay algo de contenido raw, mostrarlo
        if metadata.get('content_raw'):
            preview = metadata['content_raw'][:500]
            if len(metadata['content_raw']) > 500:
                preview += '...'

            html += f"""
                <h3>Vista previa del contenido sin procesar:</h3>
                <div class="original-content">
                    <pre>{self._escape_html(preview)}</pre>
                </div>
"""

        html += """
            </div>
        </div>
"""
        return html

    def _format_original_content(self, content_raw: str) -> str:
        """Formatea el contenido original sin procesar"""
        html = """
        <div class="original-content">
            <h3>Contenido Original (sin procesar)</h3>
            <pre>{}</pre>
        </div>
""".format(self._escape_html(content_raw[:2000]))  # Limitar a 2000 caracteres

        return html

    def _format_footer(self, metadata: Dict) -> str:
        """Formatea el pie de página del documento"""
        html = """
        <div class="footer">
            <p><strong>Documento procesado automáticamente</strong></p>
            <p>Archivo histórico DIAN - Sistema de Conceptos y Oficios</p>
"""

        # Agregar fecha de procesamiento
        html += f"""            <p>Fecha de procesamiento: {datetime.now().strftime("%d de %B de %Y - %H:%M")}</p>
"""

        # Agregar información del año y mes si está disponible
        if metadata.get('year') and metadata.get('month'):
            html += f"""            <p>Período: {metadata['month']:0>2}/{metadata['year']}</p>
"""

        # Agregar fuente si está disponible
        if metadata.get('url_fuente'):
            domain = urlparse(metadata['url_fuente']).netloc
            html += f"""            <p>Fuente: {domain}</p>
"""

        html += """        </div>"""

        return html

    def _escape_html(self, text: str) -> str:
        """Escapa caracteres HTML especiales"""
        if not text:
            return ""

        replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text