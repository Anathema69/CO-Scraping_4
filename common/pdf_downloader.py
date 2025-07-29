# scrapers/pdf_downloader.py
"""
Módulo especializado para la descarga de PDFs del Tesauro Jurídico
Maneja la generación de URLs firmadas y descarga de archivos
"""
import requests
from urllib.parse import quote
from pathlib import Path
import logging
import time
from typing import Optional, Tuple, Dict


class PDFDownloader:
    """Clase para manejar descargas de PDFs del Tesauro"""

    def __init__(self, session: requests.Session = None, pdf_dir: Path = None):
        """
        Inicializar el descargador

        Args:
            session: Sesión de requests para reutilizar
            pdf_dir: Directorio donde guardar los PDFs
        """
        self.session = session or requests.Session()
        self.pdf_dir = pdf_dir or Path("descargas_tesauro")
        self.pdf_dir.mkdir(exist_ok=True)
        self.logger = logging.getLogger(__name__)

        # Endpoint para obtener URLs firmadas
        self.sign_url_endpoint = "https://hb7a4k9770.execute-api.us-east-1.amazonaws.com/prod/sign-url-download/"

        # Headers base para las peticiones
        self.sign_headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'es-ES,es;q=0.9',
            'Origin': 'https://tesauro.supersociedades.gov.co',
            'Referer': 'https://tesauro.supersociedades.gov.co/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        self.download_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Referer': 'https://tesauro.supersociedades.gov.co/'
        }

    def get_signed_url(self, s3_path: str) -> Optional[str]:
        """
        Obtener URL firmada para descargar un archivo desde S3

        Args:
            s3_path: Ruta S3 del archivo (formato: s3://bucket/path/file.pdf)

        Returns:
            URL firmada o None si hay error
        """
        try:
            # Codificar la ruta S3 para la URL
            encoded_s3_path = quote(s3_path, safe='')
            full_url = f"{self.sign_url_endpoint}{encoded_s3_path}"

            self.logger.debug(f"Solicitando URL firmada para: {s3_path}")

            # Hacer la petición
            response = self.session.get(
                full_url,
                headers=self.sign_headers,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                signed_url = data.get('signedUrl')
                if signed_url:
                    self.logger.debug("URL firmada obtenida exitosamente")
                    return signed_url
                else:
                    self.logger.error("Respuesta sin signedUrl")
                    return None
            else:
                self.logger.error(f"Error HTTP {response.status_code}: {response.text}")
                return None

        except requests.exceptions.Timeout:
            self.logger.error("Timeout obteniendo URL firmada")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error de red: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Error inesperado: {str(e)}")
            return None

    def extract_filename_from_s3_path(self, s3_path: str) -> str:
        """
        Extraer nombre de archivo de una ruta S3

        Args:
            s3_path: Ruta S3 completa

        Returns:
            Nombre del archivo
        """
        if s3_path.startswith('s3://'):
            # Dividir la ruta y tomar el último elemento
            parts = s3_path.split('/')
            filename = parts[-1]

            # Si no tiene extensión, agregar .pdf
            if not filename.endswith('.pdf'):
                filename += '.pdf'

            return filename
        else:
            # Si no es una ruta S3 válida, generar nombre por defecto
            return f"documento_{int(time.time())}.pdf"

    def validate_pdf(self, filepath: Path) -> bool:
        """
        Validar que un archivo es un PDF válido

        Args:
            filepath: Ruta al archivo

        Returns:
            True si es un PDF válido
        """
        try:
            with open(filepath, 'rb') as f:
                header = f.read(4)
                return header == b'%PDF'
        except Exception:
            return False

    def format_date_spanish(self, date_str: str) -> str:
        """
        Convertir fecha de formato YYYY-MM-DD a formato español

        Args:
            date_str: Fecha en formato YYYY-MM-DD

        Returns:
            Fecha en formato "DD de mes del YYYY"
        """
        months = {
            '01': 'enero',
            '02': 'febrero',
            '03': 'marzo',
            '04': 'abril',
            '05': 'mayo',
            '06': 'junio',
            '07': 'julio',
            '08': 'agosto',
            '09': 'septiembre',
            '10': 'octubre',
            '11': 'noviembre',
            '12': 'diciembre'
        }

        try:
            if date_str and len(date_str) >= 10:
                year, month, day = date_str[:10].split('-')
                month_name = months.get(month, month)
                return f"{day} de {month_name} del {year}"
        except:
            pass

        return date_str  # Retornar original si hay error

    def generate_filename(self, numero_radicado: str = None, fecha_sentencia: str = None,
                          s3_path: str = None) -> str:
        """
        Generar nombre de archivo con formato específico

        Args:
            numero_radicado: Número de radicado del documento
            fecha_sentencia: Fecha de la sentencia en formato YYYY-MM-DD
            s3_path: Ruta S3 como respaldo

        Returns:
            Nombre del archivo formateado
        """
        if numero_radicado and fecha_sentencia:
            # Convertir fecha al formato español
            fecha_spanish = self.format_date_spanish(fecha_sentencia)
            # Generar nombre con formato específico
            filename = f"Superintendencia de sociedades. Sentencia N° {numero_radicado} del {fecha_spanish}.pdf"
            # Limpiar caracteres no válidos para nombres de archivo
            filename = filename.replace('/', '-').replace('\\', '-').replace(':', '-')
            return filename
        else:
            # Si no hay datos, usar el nombre del S3 o generar uno por defecto
            if s3_path:
                return self.extract_filename_from_s3_path(s3_path)
            else:
                return f"documento_{int(time.time())}.pdf"

    def download_pdf(self, s3_path: str, custom_filename: str = None,
                     numero_radicado: str = None, fecha_sentencia: str = None) -> Dict[str, any]:
        """
        Descargar un PDF completo

        Args:
            s3_path: Ruta S3 del archivo
            custom_filename: Nombre personalizado para guardar el archivo
            numero_radicado: Número de radicado para generar el nombre
            fecha_sentencia: Fecha de sentencia para generar el nombre

        Returns:
            Diccionario con información del resultado
        """
        result = {
            'success': False,
            'filename': None,
            'filepath': None,
            'size': 0,
            'error': None,
            's3_path': s3_path
        }

        try:
            # Paso 1: Obtener URL firmada
            signed_url = self.get_signed_url(s3_path)

            if not signed_url:
                result['error'] = "No se pudo obtener URL firmada"
                return result

            # Paso 2: Determinar nombre del archivo
            if custom_filename:
                filename = custom_filename
            elif numero_radicado and fecha_sentencia:
                filename = self.generate_filename(numero_radicado, fecha_sentencia, s3_path)
            else:
                filename = self.extract_filename_from_s3_path(s3_path)

            result['filename'] = filename
            filepath = self.pdf_dir / filename
            result['filepath'] = str(filepath)

            # Paso 3: Descargar el archivo
            self.logger.info(f"Descargando: {filename}")

            response = self.session.get(
                signed_url,
                headers=self.download_headers,
                timeout=60,
                stream=True
            )

            if response.status_code == 200:
                # Guardar el archivo
                total_size = 0
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_size += len(chunk)

                result['size'] = total_size

                # Validar que es un PDF
                if self.validate_pdf(filepath):
                    result['success'] = True
                    self.logger.info(f"✅ Descargado exitosamente: {filename} ({total_size:,} bytes)")
                else:
                    # Si no es un PDF válido, eliminar el archivo
                    filepath.unlink()
                    result['error'] = "El archivo descargado no es un PDF válido"
                    self.logger.error(result['error'])

            else:
                result['error'] = f"Error HTTP {response.status_code} al descargar"
                self.logger.error(result['error'])

        except requests.exceptions.Timeout:
            result['error'] = "Timeout durante la descarga"
            self.logger.error(result['error'])
        except requests.exceptions.RequestException as e:
            result['error'] = f"Error de red: {str(e)}"
            self.logger.error(result['error'])
        except Exception as e:
            result['error'] = f"Error inesperado: {str(e)}"
            self.logger.error(result['error'])

        return result

    def download_with_retry(self, s3_path: str, max_retries: int = 3,
                            retry_delay: float = 2.0, numero_radicado: str = None,
                            fecha_sentencia: str = None) -> Dict[str, any]:
        """
        Descargar con reintentos en caso de fallo

        Args:
            s3_path: Ruta S3 del archivo
            max_retries: Número máximo de reintentos
            retry_delay: Tiempo de espera entre reintentos (segundos)
            numero_radicado: Número de radicado para generar el nombre
            fecha_sentencia: Fecha de sentencia para generar el nombre

        Returns:
            Diccionario con información del resultado
        """
        last_result = None

        for attempt in range(max_retries):
            if attempt > 0:
                self.logger.info(f"Reintento {attempt}/{max_retries - 1}")
                time.sleep(retry_delay)

            result = self.download_pdf(s3_path, numero_radicado=numero_radicado,
                                       fecha_sentencia=fecha_sentencia)
            last_result = result

            if result['success']:
                return result

            # Si el error es definitivo (no es un error temporal), no reintentar
            if result['error'] and "no es un PDF válido" in result['error']:
                break

        return last_result