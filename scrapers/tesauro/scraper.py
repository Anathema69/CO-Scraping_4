# scrapers/tesauro_scraper.py
"""
Scraper principal del Tesauro Jurídico
Versión actualizada con módulo de descarga mejorado
"""
import requests
import json
import time
import csv
from datetime import datetime
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Importar el módulo de descarga
# Import desde common
from common.pdf_downloader import PDFDownloader

# Configuración
BASE_URL = "https://tesauro.supersociedades.gov.co"
API_URL = "https://admin.es.prod.ssociedades.nuvu.cc/index_thesaurus/_search"

# Headers comunes
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'es-ES,es;q=0.9',
    'Origin': BASE_URL,
    'Referer': f'{BASE_URL}/',
    'Content-Type': 'application/json',
    'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'cross-site'
}

# Mapeo de tipos de contenido entre UI y API
CONTENT_TYPE_MAPPING = {
    "Conceptos jurídicos": "Conceptos jurídicos",
    "Temas y problemas": "Temas y problemas",
    "Sentencias en formato escrito": "Sentencia procedimiento mercantil",
    "Sentencias en formato video": "Sentencia en video"
}


class TesauroScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = Path(f"logs/tesauro_{self.timestamp}")
        self.pdf_dir = Path("descargas_tesauro")
        self.setup_directories()
        self.setup_logging()
        self.results_lock = threading.Lock()

        # Inicializar el descargador de PDFs
        self.pdf_downloader = PDFDownloader(session=self.session, pdf_dir=self.pdf_dir)

    def setup_directories(self):
        """Crear directorios necesarios"""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(exist_ok=True)

    def setup_logging(self):
        """Configurar sistema de logging"""
        log_file = self.log_dir / "tesauro_scraping.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def get_filter_options(self):
        """Obtener opciones disponibles para cada filtro"""
        self.logger.info("Obteniendo opciones de filtros disponibles...")

        query = {
            "size": 0,
            "aggregations": {
                "tipos": {
                    "terms": {
                        "field": "informacion.tipo_contenido.keyword",
                        "size": 1000
                    }
                }
            }
        }

        try:
            response = self.session.post(
                f"{API_URL}?pretty",
                json=query,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                tipos = data.get('aggregations', {}).get('tipos', {}).get('buckets', [])

                self.logger.info("Tipos de contenido encontrados:")
                for tipo in tipos:
                    self.logger.info(f"  - {tipo['key']} ({tipo['doc_count']} documentos)")

                return {
                    'tipos_contenido': [t['key'] for t in tipos]
                }
            else:
                self.logger.error(f"Error obteniendo opciones: HTTP {response.status_code}")
                return {}

        except Exception as e:
            self.logger.error(f"Error obteniendo opciones: {str(e)}")
            return {}

    def build_search_query(self, filters, size=5, from_offset=0):
        """Construir query de búsqueda con filtros"""
        query = {
            "query": {
                "bool": {
                    "filter": []
                }
            },
            "size": size,
            "from": from_offset,
            "aggregations": {
                "contentType": {
                    "terms": {
                        "field": "informacion.tipo_contenido.keyword",
                        "size": 1000
                    }
                }
            }
        }

        # Agregar filtro de tipo de contenido
        if filters.get('tipo_contenido'):
            tipo_api = CONTENT_TYPE_MAPPING.get(filters['tipo_contenido'], filters['tipo_contenido'])
            query['query']['bool']['filter'].append({
                "match": {
                    "informacion.tipo_contenido": {
                        "query": tipo_api,
                        "operator": "and"
                    }
                }
            })

        # Agregar filtro de fechas
        if filters.get('fecha_desde') or filters.get('fecha_hasta'):
            date_filter = {"range": {"informacion.fecha_sentencia": {}}}

            if filters.get('fecha_desde'):
                date_filter['range']['informacion.fecha_sentencia']['gte'] = filters['fecha_desde']

            if filters.get('fecha_hasta'):
                date_filter['range']['informacion.fecha_sentencia']['lte'] = filters['fecha_hasta']

            query['query']['bool']['filter'].append(date_filter)

        # Agregar otros filtros
        if filters.get('numero_consecutivo'):
            query['query']['bool']['filter'].append({
                "match": {
                    "informacion.consecutivo": {
                        "query": filters['numero_consecutivo'],
                        "operator": "and"
                    }
                }
            })

        return query

    def search_documents(self, filters, max_results=None, page_size=50):
        """Buscar documentos con filtros aplicados"""
        self.logger.info("Iniciando búsqueda con filtros:")
        for k, v in filters.items():
            if v:
                self.logger.info(f"  {k}: {v}")

        all_results = []
        offset = 0

        while True:
            query = self.build_search_query(filters, size=page_size, from_offset=offset)

            try:
                response = self.session.post(
                    f"{API_URL}?pretty",
                    json=query,
                    timeout=30
                )

                if response.status_code != 200:
                    self.logger.error(f"Error en búsqueda: HTTP {response.status_code}")
                    break

                data = response.json()
                hits = data.get('hits', {}).get('hits', [])
                total = data.get('hits', {}).get('total', {}).get('value', 0)

                if not hits:
                    break

                # Procesar resultados
                for hit in hits:
                    doc = hit['_source']
                    result = self.extract_document_data(doc)
                    result['_id'] = hit['_id']
                    result['_score'] = hit.get('_score', 0)
                    all_results.append(result)

                self.logger.info(f"Procesados {len(all_results)} de {total} documentos")

                # Verificar límites
                if max_results and len(all_results) >= max_results:
                    all_results = all_results[:max_results]
                    break

                if len(all_results) >= total:
                    break

                offset += page_size
                time.sleep(0.5)  # Pausa entre páginas

            except Exception as e:
                self.logger.error(f"Error en búsqueda: {str(e)}")
                break

        self.logger.info(f"Búsqueda completada: {len(all_results)} documentos encontrados")
        return all_results

    def extract_document_data(self, doc):
        """Extraer datos relevantes de un documento"""
        info = doc.get('informacion', {})
        doc_principal = doc.get('documento_principal', {})

        result = {
            'titulo': doc.get('titulo', ''),
            'tipo_contenido': info.get('tipo_contenido', ''),
            'numero_radicado': info.get('numero_radicado', ''),
            'fecha_sentencia': info.get('fecha_sentencia', ''),
            'consecutivo': info.get('consecutivo', ''),
            'numero_proceso': info.get('numero_proceso', ''),
            'tramite': info.get('tramite', ''),
            'tema': info.get('tema', ''),
            'ano_expediente': info.get('ano_expediente', ''),
            'normatividad': info.get('normatividad', ''),
            'fecha_ultima_modificacion': info.get('fecha_ultima_modificacion', ''),
            'ruta_pdf': doc_principal.get('ruta_s3', ''),
            'contenido_archivo': doc_principal.get('contenido_archivo', '')[:500] + '...' if doc_principal.get(
                'contenido_archivo') else '',
            'id_relatoria': doc.get('id_relatoria', ''),
            'descriptores': [],
            'fuentes_juridicas': [],
            'partes': [],
            'estado_descarga': 'pendiente',
            'nombre_archivo': None,
            'error': None
        }

        # Procesar descriptores
        for descriptor in doc.get('descriptores', []):
            desc_text = descriptor.get('descriptor_principal', '')
            secundarios = descriptor.get('descriptores_secundarios', [])
            if secundarios:
                desc_text += f" ({', '.join(secundarios)})"
            result['descriptores'].append(desc_text)

        # Procesar fuentes jurídicas
        for fuente in doc.get('fuentes_juridicas', []):
            fuente_text = fuente.get('fuente', '')
            if fuente.get('tipo'):
                fuente_text += f" - {fuente['tipo']}"
            result['fuentes_juridicas'].append(fuente_text)

        # Procesar partes
        for parte in doc.get('partes', []):
            parte_text = f"{parte.get('nombre', '')} - {parte.get('rol', '')}"
            if parte.get('tipo_doc') and parte.get('numero_doc'):
                parte_text += f" ({parte['tipo_doc']}: {parte['numero_doc']})"
            result['partes'].append(parte_text)

        # Convertir listas a strings
        result['descriptores'] = '; '.join(result['descriptores'])
        result['fuentes_juridicas'] = '; '.join(result['fuentes_juridicas'])
        result['partes'] = '; '.join(result['partes'])

        return result

    def download_pdf_worker(self, record):
        """Worker para descargar un PDF usando el módulo PDFDownloader"""
        if not record.get('ruta_pdf'):
            with self.results_lock:
                record['estado_descarga'] = 'sin_pdf'
            return False, "No hay PDF disponible"

        try:
            s3_path = record['ruta_pdf']

            # Usar el módulo de descarga con reintentos, pasando los datos para el nombre
            result = self.pdf_downloader.download_with_retry(
                s3_path,
                max_retries=3,
                numero_radicado=record.get('numero_radicado'),
                fecha_sentencia=record.get('fecha_sentencia')
            )

            # Actualizar el registro con los resultados
            with self.results_lock:
                if result['success']:
                    record['nombre_archivo'] = result['filename']
                    record['estado_descarga'] = 'completado'
                    record['tamaño_archivo'] = result['size']
                    record['fecha_descarga'] = datetime.now().isoformat()

                    return True, f"Descargado: {result['filename']}"
                else:
                    record['error'] = result['error']
                    record['estado_descarga'] = 'error'

                    return False, result['error']

        except Exception as e:
            error_msg = f"Error inesperado: {str(e)}"
            with self.results_lock:
                record['error'] = error_msg
                record['estado_descarga'] = 'error'
            self.logger.error(f"Error descargando {record.get('numero_radicado', 'N/A')}: {error_msg}")
            return False, error_msg

    def save_results(self, results):
        """Guardar resultados en JSON y CSV"""
        # JSON completo
        json_path = self.log_dir / f'tesauro_resultados_{self.timestamp}.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # CSV
        if results:
            csv_path = self.log_dir / f'tesauro_resultados_{self.timestamp}.csv'
            csv_fields = [
                'titulo', 'tipo_contenido', 'numero_radicado', 'consecutivo',
                'fecha_sentencia', 'numero_proceso', 'tramite', 'tema',
                'normatividad', 'descriptores', 'fuentes_juridicas', 'partes',
                'nombre_archivo', 'estado_descarga', 'error'
            ]

            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(results)

        self.logger.info(f"Resultados guardados: {len(results)} documentos")

    def generate_report(self, results, filters, start_time):
        """Generar reporte final"""
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        total_docs = len(results)
        total_descargados = sum(1 for r in results if r['estado_descarga'] == 'completado')
        total_errores = sum(1 for r in results if r['estado_descarga'] == 'error')
        total_sin_pdf = sum(1 for r in results if r['estado_descarga'] == 'sin_pdf')

        # Estadísticas por tipo de contenido
        tipos_contenido = {}
        for r in results:
            tipo = r.get('tipo_contenido', 'Sin tipo')
            tipos_contenido[tipo] = tipos_contenido.get(tipo, 0) + 1

        report = {
            'fecha_ejecucion': start_time.isoformat(),
            'duracion_segundos': duration,
            'filtros_aplicados': filters,
            'resumen': {
                'total_documentos': total_docs,
                'pdfs_descargados': total_descargados,
                'errores_descarga': total_errores,
                'sin_pdf': total_sin_pdf,
                'tasa_exito': f"{(total_descargados / total_docs * 100):.2f}%" if total_docs > 0 else "0%"
            },
            'por_tipo_contenido': tipos_contenido,
            'archivos_generados': {
                'json': str(self.log_dir / f'tesauro_resultados_{self.timestamp}.json'),
                'csv': str(self.log_dir / f'tesauro_resultados_{self.timestamp}.csv'),
                'carpeta_pdfs': str(self.pdf_dir)
            }
        }

        report_path = self.log_dir / 'reporte_final.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Mostrar resumen
        print("\n" + "=" * 60)
        print("REPORTE FINAL - TESAURO JURÍDICO")
        print("=" * 60)
        print(f"Duración:            {duration:.2f} segundos")
        print(f"Total documentos:    {total_docs}")
        print(f"PDFs descargados:    {total_descargados}")
        print(f"Errores de descarga: {total_errores}")
        print(f"Sin PDF disponible:  {total_sin_pdf}")
        print(f"Tasa de éxito:       {report['resumen']['tasa_exito']}")
        print("\nPor tipo de contenido:")
        for tipo, count in sorted(tipos_contenido.items(), key=lambda x: x[1], reverse=True):
            print(f"  {tipo}: {count}")
        print("=" * 60)

        return report

    def search_and_download(self, filters, download_pdfs=True, max_results=None, max_workers=3):
        """Función principal para buscar y descargar"""
        start_time = datetime.now()

        self.logger.info("=" * 60)
        self.logger.info("INICIANDO SCRAPER DEL TESAURO JURÍDICO")
        self.logger.info("=" * 60)
        self.logger.info(f"Fecha y hora: {start_time}")
        self.logger.info(f"Descargar PDFs: {download_pdfs}")
        self.logger.info(f"Máximo resultados: {max_results if max_results else 'Sin límite'}")
        self.logger.info(f"Workers paralelos: {max_workers}")

        # Buscar documentos
        results = self.search_documents(filters, max_results)

        if not results:
            self.logger.warning("No se encontraron documentos con los filtros especificados")
            return results

        # Descargar PDFs si está habilitado
        if download_pdfs:
            self.logger.info(f"Iniciando descarga de PDFs con {max_workers} workers...")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}

                for record in results:
                    if record.get('ruta_pdf'):
                        future = executor.submit(self.download_pdf_worker, record)
                        futures[future] = record['numero_radicado']

                # Esperar a que terminen
                completed = 0
                for future in as_completed(futures):
                    completed += 1
                    if completed % 10 == 0:
                        self.logger.info(f"Progreso: {completed}/{len(futures)} descargas")

        # Guardar resultados
        self.save_results(results)

        # Generar reporte
        self.generate_report(results, filters, start_time)

        return results


# Ejemplo de uso
if __name__ == "__main__":
    scraper = TesauroScraper()

    # Ejemplo: Buscar y descargar sentencias
    filters = {
        'tipo_contenido': 'Sentencias en formato escrito',
        'fecha_desde': '2020-01-01',
        'fecha_hasta': '2025-07-24'
    }

    results = scraper.search_and_download(
        filters=filters,
        download_pdfs=True,  # Ahora funciona correctamente
        max_results=10,
        max_workers=3
    )