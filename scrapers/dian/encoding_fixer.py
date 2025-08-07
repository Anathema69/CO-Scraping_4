# encoding_fixer.py
"""
Módulo para detectar y corregir problemas de encoding y mojibake
Basado en mojibake_fixes.py con mejoras adicionales
"""

import chardet
import html
import unicodedata
import re
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


class EncodingFixer:
    """Clase para manejar problemas de encoding y mojibake en documentos DIAN"""

    def __init__(self):
        # Diccionario principal de reemplazos para mojibake
        self.mojibake_replacements = {
            # Caracteres especiales más comunes
            '�': '',  # Carácter de reemplazo Unicode
            'ï¿½': 'ñ',
            '?': '',  # Signo de interrogación usado como reemplazo cuando es excesivo

            # Vocales con tilde (minúsculas)
            'Ã¡': 'á', 'Ã©': 'é', 'Ã­': 'í', 'Ã³': 'ó', 'Ãº': 'ú',
            'á': 'á', 'é': 'é', 'í': 'í', 'ó': 'ó', 'ú': 'ú',

            # Vocales con tilde (mayúsculas)
            'Ã': 'Á', 'Ã‰': 'É', 'Ã': 'Í', 'Ã"': 'Ó', 'Ãš': 'Ú',
            'Ã': 'Á', 'É': 'É', 'Í': 'Í', 'Ó': 'Ó', 'Ú': 'Ú',

            # Letra ñ/Ñ
            'Ã±': 'ñ', 'Ã': 'Ñ', 'ñ': 'ñ', 'Ñ': 'Ñ',
            'n~': 'ñ', 'N~': 'Ñ',

            # Signos de puntuación español
            'Â¿': '¿', 'Â¡': '¡', '¿': '¿', '¡': '¡',

            # Comillas y apóstrofes
            'â€œ': '"', 'â€': '"', 'â€™': "'", 'â€˜': "'", 'â€™': "'",
            '"': '"', '"': '"', ''': "'", ''': "'",

            # Guiones y rayas
            'â€"': '—', 'â€"': '–', '—': '—', '–': '–',

            # Puntos suspensivos
            '…': '...', 'â€¦': '...',

            # Diéresis
            'Ã¼': 'ü', 'Ãœ': 'Ü', 'ü': 'ü', 'Ü': 'Ü',

            # Símbolos
            'â‚¬': '€', '€': '€', 'Â°': '°', '°': '°',
            'Â²': '²', 'Â³': '³', 'Â½': '½', 'Â¼': '¼', 'Â¾': '¾',
            'Ã—': '×', 'Ã·': '÷', 'Â±': '±',

            # Espacios especiales
            'Â ': ' ', ' ': ' ', ' ': ' ',

            # Otros caracteres latinos
            'Ã§': 'ç', 'Ã‡': 'Ç', 'Ã ': 'à', 'Ãˆ': 'È',
            'Ã¨': 'è', 'Ã¢': 'â', 'Ãª': 'ê', 'Ã´': 'ô', 'Ã®': 'î',
        }

        # Palabras comunes con problemas específicos
        self.common_word_fixes = {
            # Palabras frecuentes en documentos legales
            'Seï¿½or': 'Señor', 'seï¿½or': 'señor',
            'seï¿½ora': 'señora', 'Seï¿½ora': 'Señora',
            'aï¿½o': 'año', 'aï¿½os': 'años',
            'niï¿½o': 'niño', 'niï¿½os': 'niños', 'niï¿½a': 'niña',
            'espaï¿½ol': 'español', 'espaï¿½ola': 'española',
            'pequeï¿½o': 'pequeño', 'pequeï¿½a': 'pequeña',
            'compaï¿½ía': 'compañía', 'compaï¿½ia': 'compañía',

            # Ciudades colombianas
            'Bogotï¿½': 'Bogotá', 'BogotÃ¡': 'Bogotá',
            'MedellÃ­n': 'Medellín', 'Medellï¿½n': 'Medellín',
            'CÃºcuta': 'Cúcuta', 'Cï¿½cuta': 'Cúcuta',
            'IbaguÃ©': 'Ibagué', 'Ibaguï¿½': 'Ibagué',
            'MonterÃ­a': 'Montería', 'Monterï¿½a': 'Montería',
            'PopayÃ¡n': 'Popayán', 'Popayï¿½n': 'Popayán',

            # Términos administrativos y legales
            'administraciï¿½n': 'administración', 'administraciÃ³n': 'administración',
            'informaciï¿½n': 'información', 'informaciÃ³n': 'información',
            'resoluciï¿½n': 'resolución', 'resoluciÃ³n': 'resolución',
            'autorizaciï¿½n': 'autorización', 'autorizaciÃ³n': 'autorización',
            'facturï¿½': 'facturó', 'facturaciï¿½n': 'facturación',
            'facturaciÃ³n': 'facturación',
            'numeraciï¿½n': 'numeración', 'numeraciÃ³n': 'numeración',
            'obligaciï¿½n': 'obligación', 'obligaciÃ³n': 'obligación',
            'interpretaciï¿½n': 'interpretación', 'interpretaciÃ³n': 'interpretación',
            'aplicaciï¿½n': 'aplicación', 'aplicaciÃ³n': 'aplicación',
            'soluciï¿½n': 'solución', 'soluciÃ³n': 'solución',
            'sanciï¿½n': 'sanción', 'sanciÃ³n': 'sanción',
            'excepciï¿½n': 'excepción', 'excepciÃ³n': 'excepción',
            'direcciï¿½n': 'dirección', 'direcciÃ³n': 'dirección',
            'rÃ©gimen': 'régimen', 'rï¿½gimen': 'régimen',
            'tÃ©cnico': 'técnico', 'tï¿½cnico': 'técnico',
            'tÃ©rmino': 'término', 'tï¿½rmino': 'término',
            'pÃ¡rrafo': 'párrafo', 'pï¿½rrafo': 'párrafo',
            'artÃ­culo': 'artículo', 'artï¿½culo': 'artículo',

            # Verbos comunes
            'tambiÃ©n': 'también', 'tambiï¿½n': 'también',
            'despuÃ©s': 'después', 'despuï¿½s': 'después',
            'travÃ©s': 'través', 'travï¿½s': 'través',
            'estï¿½n': 'están', 'estÃ¡n': 'están',
            'deberï¿½n': 'deberán', 'deberÃ¡n': 'deberán',
            'seï¿½alados': 'señalados', 'seÃ±alados': 'señalados',
            'segï¿½n': 'según', 'segÃºn': 'según',
        }

        # Patrones regex para correcciones contextuales
        self.regex_patterns = [
            # Números de artículo/oficio
            (r'Art[íÃ­ï¿½]+culo\s+(\d+)', r'Artículo \1'),
            (r'N[°ÂºÂ°]+\s*(\d+)', r'N° \1'),
            (r'n[°ÂºÂ°]+\s*(\d+)', r'n° \1'),

            # Fechas con meses mal codificados
            (r'(\d+)\s+de\s+([a-z]+)(?:ï¿½|Ã±|n~)o\s+de\s+(\d{4})',
             lambda m: f"{m.group(1)} de {m.group(2)}o de {m.group(3)}"),

            # Terminaciones comunes
            (r'(\w+)ci[óÃ³ï¿½]+n\b', lambda m: m.group(1) + 'ción'),
            (r'(\w+)[íÃ­ï¿½]+a\b', lambda m: m.group(1) + 'ía'),
        ]

    def detect_and_decode(self, content_bytes: bytes) -> str:
        """
        Detecta y decodifica el contenido con el encoding correcto
        """
        # Intentar detectar el encoding
        detected = chardet.detect(content_bytes)
        encoding = detected.get('encoding', 'utf-8')
        confidence = detected.get('confidence', 0)

        logger.debug(f"Encoding detectado: {encoding} (confianza: {confidence:.2f})")

        # Lista de encodings a probar en orden de preferencia
        encodings_to_try = []

        # Si la confianza es alta, usar el detectado primero
        if confidence > 0.7 and encoding:
            encodings_to_try.append(encoding)

        # Agregar encodings comunes para documentos DIAN
        encodings_to_try.extend([
            'utf-8',
            'latin-1',
            'iso-8859-1',
            'windows-1252',
            'cp1252'
        ])

        # Eliminar duplicados manteniendo el orden
        seen = set()
        encodings_to_try = [x for x in encodings_to_try
                            if not (x in seen or seen.add(x))]

        # Intentar decodificar con cada encoding
        for enc in encodings_to_try:
            if enc:
                try:
                    decoded = content_bytes.decode(enc, errors='strict')
                    # Verificar que el resultado sea razonable
                    if self._is_valid_decoding(decoded):
                        logger.info(f"Decodificado exitosamente con {enc}")
                        return decoded
                except:
                    continue

        # Si todo falla, usar latin-1 con reemplazo de errores
        logger.warning("No se pudo decodificar con encoding específico, usando latin-1 con reemplazo")
        return content_bytes.decode('latin-1', errors='replace')

    def _is_valid_decoding(self, text: str) -> bool:
        """
        Verifica si una decodificación parece válida
        """
        # Contar caracteres problemáticos
        problematic_count = text.count('�') + text.count('ï¿½')

        # Si hay muchos caracteres problemáticos, probablemente es una mala decodificación
        if problematic_count > len(text) * 0.01:  # Más del 1% son problemáticos
            return False

        # Verificar si hay caracteres españoles comunes
        spanish_chars = 'áéíóúñÁÉÍÓÚÑ'
        has_spanish = any(char in text for char in spanish_chars)

        return True

    def fix_mojibake(self, text: str, aggressive: bool = True) -> str:
        """
        Corrige texto con problemas de mojibake
        """
        if not text:
            return text

        # Aplicar reemplazos básicos
        for old, new in self.mojibake_replacements.items():
            text = text.replace(old, new)

        # Aplicar correcciones de palabras comunes
        for old, new in self.common_word_fixes.items():
            text = text.replace(old, new)

        # Aplicar patrones regex
        for pattern, replacement in self.regex_patterns:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # Decodificar entidades HTML
        text = html.unescape(text)

        # Limpiar caracteres de control (excepto saltos de línea y tabulaciones)
        text = ''.join(char for char in text
                       if unicodedata.category(char)[0] != 'C' or char in '\n\r\t')

        if aggressive:
            # Correcciones agresivas para caracteres aislados
            text = self._fix_isolated_replacement_chars(text)

            # Correcciones adicionales específicas de DIAN
            text = self._fix_dian_specific_issues(text)

        # Normalizar espacios múltiples
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text

    def _fix_isolated_replacement_chars(self, text: str) -> str:
        """
        Intenta corregir caracteres de reemplazo basándose en el contexto
        """
        # Patrones contextuales para � aislados
        contextual_fixes = [
            # � entre consonantes probablemente es una vocal con tilde
            (r'([bcdfghjklmnpqrstvwxyz])�([bcdfghjklmnpqrstvwxyz])', r'\1í\2'),

            # � al final de palabra precedido por 'ci' probablemente es 'ón'
            (r'ci�n\b', 'ción'),

            # � después de 'a' al inicio de palabra probablemente es 'ñ'
            (r'\ba�o', 'año'),

            # � en medio de 'se' y 'or' probablemente es 'ñ'
            (r'\bse�or', 'señor'),

            # Números con � probablemente son grados o números ordinales
            (r'(\d+)�', r'\1°'),
        ]

        for pattern, replacement in contextual_fixes:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        return text

    def _fix_dian_specific_issues(self, text: str) -> str:
        """
        Correcciones específicas para documentos DIAN
        """
        # Términos específicos de DIAN que suelen tener problemas
        dian_fixes = {
            'DIANï¿½': 'DIAN',
            'tributaciï¿½n': 'tributación',
            'tributaciÃ³n': 'tributación',
            'contribuciï¿½n': 'contribución',
            'contribuciÃ³n': 'contribución',
            'declaraciï¿½n': 'declaración',
            'declaraciÃ³n': 'declaración',
            'retenciï¿½n': 'retención',
            'retenciÃ³n': 'retención',
            'devoluciï¿½n': 'devolución',
            'devoluciÃ³n': 'devolución',
            'compensaciï¿½n': 'compensación',
            'compensaciÃ³n': 'compensación',
        }

        for old, new in dian_fixes.items():
            text = text.replace(old, new)

        # Corregir formato de RUT/NIT
        text = re.sub(r'(\d{3})\.(\d{3})\.(\d{3})-(\d)', r'\1.\2.\3-\4', text)

        return text

    def detect_encoding_issues(self, text: str) -> Dict:
        """
        Detecta si un texto tiene problemas de encoding
        """
        issues = {
            'has_replacement_chars': '�' in text,
            'has_mojibake': any(pattern in text for pattern in
                                ['Ã¡', 'Ã©', 'Ã­', 'Ã³', 'Ãº', 'Ã±', 'ï¿½']),
            'has_excessive_question_marks': text.count('?') > len(text) * 0.05,
            'replacement_char_count': text.count('�'),
            'mojibake_char_count': 0,
            'suspicious_patterns': [],
            'needs_fixing': False
        }

        # Contar caracteres mojibake
        mojibake_patterns = ['Ã¡', 'Ã©', 'Ã­', 'Ã³', 'Ãº', 'Ã±', 'ï¿½', 'Â¿', 'Â¡']
        for pattern in mojibake_patterns:
            issues['mojibake_char_count'] += text.count(pattern)

        # Buscar patrones sospechosos
        suspicious = [
            ('Ã', 'Posible UTF-8 interpretado como Latin-1'),
            ('ï¿½', 'Carácter de reemplazo Unicode'),
            ('Â', 'Posible doble codificación'),
            ('â€', 'Comillas smart mal codificadas'),
        ]

        for pattern, description in suspicious:
            if pattern in text:
                issues['suspicious_patterns'].append({
                    'pattern': pattern,
                    'description': description,
                    'count': text.count(pattern)
                })

        # Determinar si necesita corrección
        issues['needs_fixing'] = (
                issues['has_replacement_chars'] or
                issues['has_mojibake'] or
                issues['mojibake_char_count'] > 0 or
                len(issues['suspicious_patterns']) > 0
        )

        return issues

    def clean_text(self, text: str, aggressive: bool = True, debug: bool = False) -> str:
        """
        Función principal para limpiar texto con problemas de encoding
        """
        if not text:
            return text

        if debug:
            print("=== Análisis de encoding ===")
            issues = self.detect_encoding_issues(text)
            print(f"Caracteres de reemplazo: {issues['replacement_char_count']}")
            print(f"Caracteres mojibake: {issues['mojibake_char_count']}")
            print(f"Tiene mojibake: {issues['has_mojibake']}")
            if issues['suspicious_patterns']:
                print("Patrones sospechosos encontrados:")
                for p in issues['suspicious_patterns']:
                    print(f"  - {p['description']}: {p['count']} ocurrencias")

        # Aplicar correcciones
        cleaned = self.fix_mojibake(text, aggressive=aggressive)

        if debug:
            remaining_issues = self.detect_encoding_issues(cleaned)
            print(f"\n=== Después de limpieza ===")
            print(f"Caracteres de reemplazo restantes: {remaining_issues['replacement_char_count']}")
            print(f"Caracteres mojibake restantes: {remaining_issues['mojibake_char_count']}")

        return cleaned