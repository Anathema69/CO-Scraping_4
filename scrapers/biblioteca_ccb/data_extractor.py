import csv
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd


class BibliotecaCCBDataExtractor:
    """Extractor de datos para laudos arbitrales de la CCB"""

    def __init__(self, data_dir: str = "laudos_arbitraje"):
        self.data_dir = Path(data_dir)
        self.logger = logging.getLogger(__name__)

    def extract_metadata(self) -> List[Dict]:
        """Extrae metadata del archivo CSV generado por el scraper"""
        metadata_file = self.data_dir / "laudos_metadata.csv"

        if not metadata_file.exists():
            self.logger.warning(f"No se encontró archivo de metadata: {metadata_file}")
            return []

        try:
            # Leer CSV con pandas para mejor manejo
            df = pd.read_csv(metadata_file, encoding='utf-8')

            # Convertir a lista de diccionarios
            records = df.to_dict('records')

            # Procesar cada registro
            processed_records = []
            for record in records:
                processed_record = {
                    'id': record.get('id', ''),
                    'handle': record.get('handle', ''),
                    'titulo': record.get('name', ''),
                    'fecha': record.get('fecha', ''),
                    'demandante': record.get('demandante', ''),
                    'demandado': record.get('demandado', ''),
                    'arbitros': record.get('arbitros', ''),
                    'materias': record.get('materias', ''),
                    'descripcion': record.get('descripcion', ''),
                    'archivo_pdf': self._find_pdf_file(record)
                }
                processed_records.append(processed_record)

            return processed_records

        except Exception as e:
            self.logger.error(f"Error extrayendo metadata: {e}")
            return []

    def _find_pdf_file(self, record: Dict) -> Optional[str]:
        """Busca el archivo PDF correspondiente al registro"""
        pdf_dir = self.data_dir / "pdfs"
        if not pdf_dir.exists():
            return None

        # Buscar por fecha y título
        fecha = record.get('fecha', 'sin_fecha')
        titulo = record.get('name', '')

        # Limpiar título para nombre de archivo
        safe_title = titulo[:200]  # Limitar longitud
        for char in '<>:"/\\|?*':
            safe_title = safe_title.replace(char, '_')

        # Buscar archivo que coincida
        pattern = f"{fecha}_{safe_title}*.pdf"
        matching_files = list(pdf_dir.glob(pattern))

        if matching_files:
            return str(matching_files[0].relative_to(self.data_dir))

        return None

    def get_statistics(self) -> Dict:
        """Obtiene estadísticas de los datos extraídos"""
        records = self.extract_metadata()

        if not records:
            return {
                'total_laudos': 0,
                'con_pdf': 0,
                'sin_pdf': 0,
                'por_año': {},
                'por_materia': {},
                'arbitros_frecuentes': []
            }

        # Estadísticas básicas
        total = len(records)
        con_pdf = sum(1 for r in records if r.get('archivo_pdf'))

        # Por año
        por_año = {}
        for record in records:
            fecha = record.get('fecha', '')
            if fecha and len(fecha) >= 4:
                año = fecha[:4]
                por_año[año] = por_año.get(año, 0) + 1

        # Por materia
        por_materia = {}
        for record in records:
            materias = record.get('materias', '')
            if materias:
                for materia in materias.split(';'):
                    materia = materia.strip()
                    if materia:
                        por_materia[materia] = por_materia.get(materia, 0) + 1

        # Árbitros más frecuentes
        arbitros_count = {}
        for record in records:
            arbitros = record.get('arbitros', '')
            if arbitros:
                for arbitro in arbitros.split(';'):
                    arbitro = arbitro.strip()
                    if arbitro:
                        arbitros_count[arbitro] = arbitros_count.get(arbitro, 0) + 1

        arbitros_frecuentes = sorted(
            arbitros_count.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return {
            'total_laudos': total,
            'con_pdf': con_pdf,
            'sin_pdf': total - con_pdf,
            'por_año': por_año,
            'por_materia': dict(sorted(
                por_materia.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]),
            'arbitros_frecuentes': [
                {'nombre': nombre, 'cantidad': cantidad}
                for nombre, cantidad in arbitros_frecuentes
            ]
        }

    def export_to_json(self, output_file: str = None) -> str:
        """Exporta los datos a formato JSON"""
        if output_file is None:
            output_file = self.data_dir / "laudos_data.json"
        else:
            output_file = Path(output_file)

        records = self.extract_metadata()
        stats = self.get_statistics()

        data = {
            'metadata': {
                'fuente': 'Biblioteca Digital CCB - Centro de Arbitraje',
                'fecha_extraccion': str(Path(self.data_dir / "laudos_metadata.csv").stat().st_mtime
                                        if (self.data_dir / "laudos_metadata.csv").exists() else ''),
                'total_registros': len(records)
            },
            'estadisticas': stats,
            'laudos': records
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Datos exportados a: {output_file}")
        return str(output_file)

    def search_laudos(self, **kwargs) -> List[Dict]:
        """
        Busca laudos según criterios

        Kwargs:
            demandante: str
            demandado: str
            arbitro: str
            materia: str
            año: str
            fecha_desde: str
            fecha_hasta: str
        """
        records = self.extract_metadata()
        results = records

        # Filtrar por demandante
        if kwargs.get('demandante'):
            demandante = kwargs['demandante'].lower()
            results = [r for r in results if demandante in r.get('demandante', '').lower()]

        # Filtrar por demandado
        if kwargs.get('demandado'):
            demandado = kwargs['demandado'].lower()
            results = [r for r in results if demandado in r.get('demandado', '').lower()]

        # Filtrar por árbitro
        if kwargs.get('arbitro'):
            arbitro = kwargs['arbitro'].lower()
            results = [r for r in results if arbitro in r.get('arbitros', '').lower()]

        # Filtrar por materia
        if kwargs.get('materia'):
            materia = kwargs['materia'].lower()
            results = [r for r in results if materia in r.get('materias', '').lower()]

        # Filtrar por año
        if kwargs.get('año'):
            año = kwargs['año']
            results = [r for r in results if r.get('fecha', '').startswith(año)]

        # Filtrar por rango de fechas
        if kwargs.get('fecha_desde') or kwargs.get('fecha_hasta'):
            fecha_desde = kwargs.get('fecha_desde', '0000-00-00')
            fecha_hasta = kwargs.get('fecha_hasta', '9999-12-31')
            results = [
                r for r in results
                if fecha_desde <= r.get('fecha', '') <= fecha_hasta
            ]

        return results