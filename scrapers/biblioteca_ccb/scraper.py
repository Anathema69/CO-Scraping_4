# scrapers/biblioteca_ccb/scraper.py
import json
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

try:
    from .ccb_scraper_patched import CCBArbitrajeScraper
except ImportError:
    from scrapers.biblioteca_ccb.ccb_scraper_patched import CCBArbitrajeScraper


class BibliotecaCCBScraper:
    """Scraper para la Biblioteca Digital CCB - Centro de Arbitraje"""

    def __init__(self, output_dir: str = "descargas_biblioteca"):
        # Generar timestamp único para esta ejecución
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Directorio de PDFs (siguiendo el patrón de otros scrapers)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Directorio de logs específico para esta ejecución
        self.log_dir = Path(f"logs/biblioteca_ccb_{self.timestamp}")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Configurar logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # El scraper base manejará todo internamente con los directorios correctos
        self.scraper = None

        # Variables para estadísticas
        self.stats = {
            'expected': 0,
            'processed': 0,
            'downloaded': 0,
            'failed': 0,
            'start_time': None,
            'end_time': None
        }

    # En el archivo scrapers/biblioteca_ccb/scraper.py, actualizar el método run:

    def run(self, date_filter: str = None, limit: int = None,
            browse_type: str = 'dateissued', author_filter: str = None,
            subject_filter: str = None, title_filter: str = None) -> Dict:
        """
        Ejecuta el scraper con filtros específicos

        Args:
            date_filter: Filtro de fecha (ej: "2024" o "2024-01")
            limit: Límite de documentos a procesar
            browse_type: Tipo de búsqueda ('dateissued' o 'author')
            author_filter: Nombre del autor para búsqueda por autor
            subject_filter: Nombre de la materia para búsqueda por materia
            title_filter: Título para búsqueda por título
        Returns:
            Dict con estadísticas de la ejecución
        """
        self.stats['start_time'] = datetime.now()

        # Validaciones según el tipo de búsqueda
        if browse_type == 'dateissued' and date_filter:
            # Validar filtro de fecha
            if "-" in date_filter:
                parts = date_filter.split("-")
                if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
                    raise ValueError("Formato de fecha inválido. Use: 'YYYY' o 'YYYY-MM'")
            elif len(date_filter) != 4:
                raise ValueError("Formato de año inválido. Use: 'YYYY'")

            self.logger.info(f"Ejecutando búsqueda por fecha con filtro: {date_filter}")

        elif browse_type == 'author':
            if not author_filter:
                raise ValueError("Se requiere el nombre del autor para búsqueda por autor")

            self.logger.info(f"Ejecutando búsqueda por autor: {author_filter}")

            # IMPORTANTE: En este punto, author_filter ya debe ser el nombre exacto
            # La resolución de nombres parciales se hace en app.py antes de llegar aquí

        elif browse_type == 'subject':
            if not subject_filter:
                raise ValueError("Se requiere el nombre de la materia para búsqueda por materia")

            self.logger.info(f"Ejecutando búsqueda por materia: {subject_filter}")

        elif browse_type == 'title':
            if not title_filter:
                raise ValueError("Se requiere el título para búsqueda por título")

            self.logger.info(f"Ejecutando búsqueda por título: {title_filter}")
        else:
            self.logger.info("Ejecutando búsqueda sin filtros (todos los documentos)")

        try:
            # Inicializar el scraper base con los directorios correctos
            self.scraper = CCBArbitrajeScraper(
                output_dir=str(self.output_dir),
                log_dir=str(self.log_dir),
                timestamp=self.timestamp,
                max_workers=5
            )

            # Guardar información del filtro para el reporte
            self.filter_info = {
                'tipo': browse_type,
                'valor': author_filter if browse_type == 'author' else
                    subject_filter if browse_type == 'subject' else
                    title_filter if browse_type == 'title' else
                    date_filter
            }

            # Ejecutar el scraper según el tipo de búsqueda
            if browse_type == 'author':
                self.scraper.run(
                    limit=limit,
                    rpp=40,
                    browse_type='author',
                    author_filter=author_filter
                )
            elif browse_type == 'subject':
                self.scraper.run(
                    limit=limit,
                    rpp=40,
                    browse_type='subject',
                    subject_filter=subject_filter
                )
            elif browse_type == 'title':
                self.scraper.run(
                    limit=limit,
                    rpp=40,
                    browse_type='title',
                    title_filter=title_filter
                )
            else:
                self.scraper.run(
                    limit=limit,
                    rpp=40,
                    date_filter=date_filter
                )

            # Actualizar estadísticas desde el progreso del scraper
            if hasattr(self.scraper, 'progress'):
                self.stats['downloaded'] = len(self.scraper.progress.get('downloaded', []))
                self.stats['failed'] = len(self.scraper.progress.get('failed', []))
                self.stats['processed'] = self.stats['downloaded'] + self.stats['failed']
                self.stats['expected'] = self.scraper.progress.get('total_items', 0)

                # Si no hay total_items, usar el procesado como expected
                if self.stats['expected'] == 0:
                    self.stats['expected'] = self.stats['processed']

                self.logger.info(
                    f"Estadísticas finales - Total: {self.stats['expected']}, "
                    f"Descargados: {self.stats['downloaded']}, Fallidos: {self.stats['failed']}"
                )

        except Exception as e:
            self.logger.error(f"Error durante la ejecución: {e}")
            raise
        finally:
            self.stats['end_time'] = datetime.now()

        return self.generate_report()

    def generate_report(self) -> Dict:
        """Genera reporte de estadísticas"""
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()

        # Calcular tamaño total de archivos descargados
        total_size = 0
        if self.output_dir.exists():
            for pdf_file in self.output_dir.glob("*.pdf"):
                total_size += pdf_file.stat().st_size

        return {
            'status': 'completed',
            'stats': {
                'expected': self.stats['expected'],
                'processed': self.stats['processed'],
                'downloaded': self.stats['downloaded'],
                'failed': self.stats['failed'],
                'success_rate': (self.stats['downloaded'] / self.stats['processed'] * 100)
                if self.stats['processed'] > 0 else 0
            },
            'duration': duration,
            'total_size': total_size,
            'start_time': self.stats['start_time'].isoformat(),
            'end_time': self.stats['end_time'].isoformat(),
            'output_dir': str(self.output_dir),
            'log_dir': str(self.log_dir),
            'timestamp': self.timestamp
        }

    def get_progress(self) -> Dict:
        """Obtiene el progreso actual"""
        # Actualizar estadísticas en tiempo real
        if self.scraper and hasattr(self.scraper, 'progress'):
            self.stats['downloaded'] = len(self.scraper.progress.get('downloaded', []))
            self.stats['failed'] = len(self.scraper.progress.get('failed', []))
            self.stats['processed'] = self.stats['downloaded'] + self.stats['failed']

            # Obtener el total esperado del scraper
            total_from_scraper = self.scraper.progress.get('total_items', 0)
            if total_from_scraper > 0:
                self.stats['expected'] = total_from_scraper
            elif self.stats['expected'] == 0 and self.stats['processed'] > 0:
                # Si no hay total, mostrar el procesado actual
                self.stats['expected'] = self.stats['processed']

        return {
            'expected': self.stats['expected'],
            'processed': self.stats['processed'],
            'downloaded': self.stats['downloaded'],
            'failed': self.stats['failed'],
            'in_progress': True
        }

    def get_authors_preview(self, letter: str = None) -> List[Dict]:
        """
        Obtiene una vista previa de autores disponibles

        Args:
            letter: Letra inicial para filtrar (opcional)

        Returns:
            Lista de autores con sus cantidades
        """
        # Crear scraper temporal para obtener lista de autores
        temp_scraper = CCBArbitrajeScraper(
            output_dir=str(self.output_dir),
            log_dir=str(self.log_dir),
            timestamp=self.timestamp
        )

        return temp_scraper.get_authors_list(letter)