# scrapers/download_manager.py
"""
Gestor de descargas con control de concurrencia y manejo de errores
"""
import requests
from pathlib import Path
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Callable, Tuple
from urllib.parse import unquote
import re


class DownloadManager:
    """Gestiona las descargas de PDFs con concurrencia controlada"""

    def __init__(self, pdf_dir: Path, base_headers: dict, pdf_url: str):
        self.pdf_dir = pdf_dir
        self.base_headers = base_headers
        self.pdf_url = pdf_url
        self.logger = logging.getLogger(__name__)

        # Configuración de descargas
        self.max_workers = 3
        self.download_timeout = 60
        self.max_retries = 3
        self.retry_delay = 2.0

        # Estado de descargas
        self.download_queue = []
        self.active_downloads = {}
        self.completed_downloads = 0
        self.failed_downloads = 0
        self.results_lock = threading.Lock()

        # Pool de threads
        self.executor = None
        self.futures = {}

        # Callbacks
        self.progress_callback = None
        self.completion_callback = None

    def initialize(self, max_workers: int = 3):
        """Inicializar el pool de descargas"""
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.logger.info(f"📥 Pool de descargas iniciado con {max_workers} workers")

    def shutdown(self, wait: bool = True):
        """Cerrar el pool de descargas"""
        if self.executor:
            self.executor.shutdown(wait=wait)
            self.logger.info("📥 Pool de descargas cerrado")

    def queue_download(self, record: Dict) -> bool:
        """
        Agregar un documento a la cola de descarga

        Args:
            record: Diccionario con información del documento

        Returns:
            True si se agregó exitosamente
        """
        if not record.get('id'):
            return False

        # Verificar si ya está en proceso
        with self.results_lock:
            if record['id'] in self.active_downloads:
                self.logger.debug(f"Documento {record['id']} ya está en descarga")
                return False

            # Marcar como activo
            self.active_downloads[record['id']] = {
                'status': 'queued',
                'start_time': time.time()
            }

        # Enviar al pool
        future = self.executor.submit(self._download_worker, record)
        self.futures[future] = record['id']

        self.logger.debug(f"📥 Documento {record['id']} agregado a la cola")
        return True

    def _download_worker(self, record: Dict) -> Tuple[bool, str]:
        """Worker que ejecuta la descarga de un PDF"""
        doc_id = record['id']

        try:
            # Actualizar estado
            with self.results_lock:
                self.active_downloads[doc_id]['status'] = 'downloading'

            # Intentar descarga con reintentos
            for attempt in range(self.max_retries):
                try:
                    success, message = self._attempt_download(record)

                    if success:
                        with self.results_lock:
                            self.completed_downloads += 1
                            del self.active_downloads[doc_id]

                        if self.progress_callback:
                            self.progress_callback(self.completed_downloads, self.failed_downloads)

                        return True, message

                except Exception as e:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    else:
                        raise

            # Si llegamos aquí, todos los intentos fallaron
            raise Exception(f"Agotados {self.max_retries} intentos")

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"❌ Error descargando {doc_id}: {error_msg}")

            with self.results_lock:
                self.failed_downloads += 1
                record['error'] = error_msg
                record['estado_descarga'] = 'error'
                del self.active_downloads[doc_id]

            if self.progress_callback:
                self.progress_callback(self.completed_downloads, self.failed_downloads)

            return False, error_msg

    def _attempt_download(self, record: Dict) -> Tuple[bool, str]:
        """Intentar descargar un archivo PDF"""
        doc_id = record['id']

        # Crear sesión temporal para esta descarga
        session = requests.Session()
        session.headers.update(self.base_headers)

        try:
            # Parámetros de descarga
            pdf_params = {
                'corp': 'csj',
                'ext': 'pdf',
                'file': doc_id
            }

            # Realizar petición
            response = session.get(
                self.pdf_url,
                params=pdf_params,
                timeout=self.download_timeout,
                stream=True
            )

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")

            # Obtener nombre del archivo
            content_disposition = response.headers.get('Content-Disposition')
            filename = self._extract_filename(content_disposition, doc_id)

            # Descargar contenido
            content = b''
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content += chunk

            # Validar PDF
            if len(content) < 1000 or not content.startswith(b'%PDF'):
                raise Exception("Archivo no válido o muy pequeño")

            # Guardar archivo
            filepath = self.pdf_dir / filename
            with open(filepath, 'wb') as f:
                f.write(content)

            # Actualizar registro
            with self.results_lock:
                record['nombre_archivo'] = filename
                record['estado_descarga'] = 'completado'
                record['tamaño_archivo'] = len(content)
                record['fecha_descarga'] = time.strftime('%Y-%m-%d %H:%M:%S')

            self.logger.info(f"✅ Descargado: {filename} ({len(content):,} bytes)")
            return True, f"Descargado: {filename}"

        finally:
            session.close()

    def _extract_filename(self, disposition: Optional[str], doc_id: str) -> str:
        """Extraer nombre de archivo de Content-Disposition"""
        if not disposition:
            return f"{doc_id}.pdf"

        patterns = [
            r"filename\*=UTF-8''(?P<fname>[^;]+)",
            r'filename="(?P<fname>[^"]+)"',
            r'filename=([^;]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, disposition)
            if match:
                if 'fname' in match.groupdict():
                    return unquote(match.group('fname'))
                else:
                    return match.group(1).strip()

        return f"{doc_id}.pdf"

    def process_completed_downloads(self) -> List[str]:
        """Procesar y obtener información de descargas completadas"""
        completed = []

        for future in list(self.futures.keys()):
            if future.done():
                doc_id = self.futures[future]
                try:
                    success, message = future.result()
                    if success:
                        completed.append(doc_id)
                except Exception as e:
                    self.logger.error(f"Error procesando resultado de {doc_id}: {e}")

                # Limpiar future completado
                del self.futures[future]

        return completed

    def wait_for_all(self, timeout: Optional[float] = None) -> Dict[str, int]:
        """
        Esperar a que terminen todas las descargas

        Args:
            timeout: Tiempo máximo de espera en segundos

        Returns:
            Diccionario con estadísticas finales
        """
        self.logger.info(f"⏳ Esperando {len(self.futures)} descargas pendientes...")

        start_time = time.time()

        for future in as_completed(self.futures.keys(), timeout=timeout):
            doc_id = self.futures[future]

            try:
                success, message = future.result()
                if self.completion_callback:
                    self.completion_callback(doc_id, success, message)

            except Exception as e:
                self.logger.error(f"Error en descarga {doc_id}: {e}")
                if self.completion_callback:
                    self.completion_callback(doc_id, False, str(e))

        elapsed = time.time() - start_time

        stats = {
            'completed': self.completed_downloads,
            'failed': self.failed_downloads,
            'total': self.completed_downloads + self.failed_downloads,
            'success_rate': (self.completed_downloads / (self.completed_downloads + self.failed_downloads) * 100)
            if (self.completed_downloads + self.failed_downloads) > 0 else 0,
            'elapsed_time': elapsed
        }

        self.logger.info(
            f"✅ Descargas finalizadas: {stats['completed']} exitosas, "
            f"{stats['failed']} fallidas ({stats['success_rate']:.1f}% éxito)"
        )

        return stats

    def get_active_downloads(self) -> List[str]:
        """Obtener lista de descargas activas"""
        with self.results_lock:
            return list(self.active_downloads.keys())

    def get_download_stats(self) -> Dict[str, any]:
        """Obtener estadísticas actuales de descarga"""
        with self.results_lock:
            active_count = len(self.active_downloads)
            queued_count = sum(1 for d in self.active_downloads.values() if d['status'] == 'queued')
            downloading_count = sum(1 for d in self.active_downloads.values() if d['status'] == 'downloading')

        return {
            'completed': self.completed_downloads,
            'failed': self.failed_downloads,
            'active': active_count,
            'queued': queued_count,
            'downloading': downloading_count,
            'pending_futures': len(self.futures)
        }

    def set_progress_callback(self, callback: Callable[[int, int], None]):
        """Establecer callback de progreso"""
        self.progress_callback = callback

    def set_completion_callback(self, callback: Callable[[str, bool, str], None]):
        """Establecer callback de completación"""
        self.completion_callback = callback