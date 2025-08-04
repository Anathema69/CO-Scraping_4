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

    def __init__(self, output_dir: str = "laudos_arbitraje"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Configurar logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Inicializar el scraper base
        self.scraper = CCBArbitrajeScraper(output_dir=output_dir, max_workers=5)

        # Variables para estadísticas
        self.stats = {
            'expected': 0,
            'processed': 0,
            'downloaded': 0,
            'failed': 0,
            'start_time': None,
            'end_time': None
        }

    def run(self, date_filter: str = None, limit: int = None) -> Dict:
        """
        Ejecuta el scraper con filtros específicos

        Args:
            date_filter: Filtro de fecha (ej: "2024" o "2024-01")
            limit: Límite de documentos a procesar

        Returns:
            Dict con estadísticas de la ejecución
        """
        self.stats['start_time'] = datetime.now()

        # Validar filtro de fecha
        if date_filter:
            if "-" in date_filter:
                parts = date_filter.split("-")
                if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
                    raise ValueError("Formato de fecha inválido. Use: 'YYYY' o 'YYYY-MM'")
            elif len(date_filter) != 4:
                raise ValueError("Formato de año inválido. Use: 'YYYY'")

        self.logger.info(f"Ejecutando búsqueda con filtro: {date_filter}")

        try:
            # Ejecutar el scraper base directamente
            # El scraper base maneja la paginación correctamente
            self.scraper.run(limit=limit, rpp=40, date_filter=date_filter)

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
                    f"Estadísticas finales - Total: {self.stats['expected']}, Descargados: {self.stats['downloaded']}, Fallidos: {self.stats['failed']}")

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
        pdf_dir = self.output_dir / "pdfs"
        if pdf_dir.exists():
            for pdf_file in pdf_dir.glob("*.pdf"):
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
            'output_dir': str(self.output_dir)
        }

    def get_progress(self) -> Dict:
        """Obtiene el progreso actual"""
        # Actualizar estadísticas en tiempo real
        if hasattr(self.scraper, 'progress'):
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