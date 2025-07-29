# scrapers/download_stats.py
"""
Módulo para generar estadísticas y reportes de las descargas
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import csv


class DownloadStats:
    """Clase para manejar estadísticas de descarga"""

    def __init__(self, log_dir: Path):
        """
        Inicializar el manejador de estadísticas

        Args:
            log_dir: Directorio donde se guardan los logs
        """
        self.log_dir = log_dir
        self.stats_file = log_dir / "download_stats.json"
        self.stats = self.load_stats()

    def load_stats(self) -> Dict[str, Any]:
        """Cargar estadísticas existentes o crear nuevas"""
        if self.stats_file.exists():
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {
                'total_downloads': 0,
                'successful_downloads': 0,
                'failed_downloads': 0,
                'total_size_bytes': 0,
                'downloads_by_type': {},
                'errors_by_type': {},
                'download_times': [],
                'last_update': None
            }

    def save_stats(self):
        """Guardar estadísticas actualizadas"""
        self.stats['last_update'] = datetime.now().isoformat()
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2)

    def update_download(self, record: Dict[str, Any], success: bool,
                        download_time: float = None, file_size: int = None):
        """
        Actualizar estadísticas con un resultado de descarga

        Args:
            record: Registro del documento
            success: Si la descarga fue exitosa
            download_time: Tiempo de descarga en segundos
            file_size: Tamaño del archivo en bytes
        """
        self.stats['total_downloads'] += 1

        if success:
            self.stats['successful_downloads'] += 1
            if file_size:
                self.stats['total_size_bytes'] += file_size
            if download_time:
                self.stats['download_times'].append(download_time)
        else:
            self.stats['failed_downloads'] += 1

            # Registrar tipo de error
            error = record.get('error', 'Error desconocido')
            error_type = self._classify_error(error)
            self.stats['errors_by_type'][error_type] = \
                self.stats['errors_by_type'].get(error_type, 0) + 1

        # Actualizar por tipo de contenido
        tipo = record.get('tipo_contenido', 'Sin tipo')
        if tipo not in self.stats['downloads_by_type']:
            self.stats['downloads_by_type'][tipo] = {
                'total': 0,
                'successful': 0,
                'failed': 0
            }

        self.stats['downloads_by_type'][tipo]['total'] += 1
        if success:
            self.stats['downloads_by_type'][tipo]['successful'] += 1
        else:
            self.stats['downloads_by_type'][tipo]['failed'] += 1

        self.save_stats()

    def _classify_error(self, error: str) -> str:
        """Clasificar el tipo de error"""
        error_lower = error.lower()

        if 'timeout' in error_lower:
            return 'timeout'
        elif 'url firmada' in error_lower:
            return 'signed_url_error'
        elif 'http' in error_lower:
            return 'http_error'
        elif 'red' in error_lower or 'network' in error_lower:
            return 'network_error'
        elif 'pdf válido' in error_lower:
            return 'invalid_pdf'
        else:
            return 'other'

    def get_summary(self) -> Dict[str, Any]:
        """Obtener resumen de estadísticas"""
        total = self.stats['total_downloads']
        successful = self.stats['successful_downloads']

        if total > 0:
            success_rate = (successful / total) * 100
        else:
            success_rate = 0

        avg_download_time = 0
        if self.stats['download_times']:
            avg_download_time = sum(self.stats['download_times']) / len(self.stats['download_times'])

        return {
            'total_downloads': total,
            'successful_downloads': successful,
            'failed_downloads': self.stats['failed_downloads'],
            'success_rate': f"{success_rate:.2f}%",
            'total_size_mb': self.stats['total_size_bytes'] / (1024 * 1024),
            'average_download_time_seconds': avg_download_time,
            'downloads_by_type': self.stats['downloads_by_type'],
            'errors_by_type': self.stats['errors_by_type'],
            'last_update': self.stats['last_update']
        }

    def generate_csv_report(self, results: List[Dict[str, Any]]):
        """
        Generar reporte CSV detallado

        Args:
            results: Lista de resultados de búsqueda
        """
        csv_path = self.log_dir / "download_report.csv"

        # Campos para el CSV
        fields = [
            'numero_radicado',
            'titulo',
            'tipo_contenido',
            'fecha_sentencia',
            'estado_descarga',
            'nombre_archivo',
            'tamaño_archivo',
            'fecha_descarga',
            'error',
            'ruta_pdf'
        ]

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()

            for result in results:
                # Filtrar solo los que tienen información de descarga
                if result.get('estado_descarga') != 'pendiente':
                    writer.writerow(result)

        return csv_path

    def print_summary(self):
        """Imprimir resumen en consola"""
        summary = self.get_summary()

        print("\n" + "=" * 60)
        print("📊 ESTADÍSTICAS DE DESCARGA")
        print("=" * 60)
        print(f"Total intentos:      {summary['total_downloads']}")
        print(f"Descargas exitosas:  {summary['successful_downloads']}")
        print(f"Descargas fallidas:  {summary['failed_downloads']}")
        print(f"Tasa de éxito:       {summary['success_rate']}")
        print(f"Tamaño total:        {summary['total_size_mb']:.2f} MB")

        if summary['average_download_time_seconds'] > 0:
            print(f"Tiempo promedio:     {summary['average_download_time_seconds']:.2f} segundos")

        if summary['downloads_by_type']:
            print("\nPor tipo de contenido:")
            for tipo, stats in summary['downloads_by_type'].items():
                print(f"  {tipo}:")
                print(f"    - Total: {stats['total']}")
                print(f"    - Exitosas: {stats['successful']}")
                print(f"    - Fallidas: {stats['failed']}")

        if summary['errors_by_type']:
            print("\nErrores por tipo:")
            for error_type, count in summary['errors_by_type'].items():
                print(f"  {error_type}: {count}")

        print("=" * 60)