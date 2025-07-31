# scrapers/consejo_estado/scraper.py
"""
Scraper principal del Consejo de Estado - SAMAI
"""
import time
import json
from datetime import datetime
from pathlib import Path
import logging
from typing import List, Dict, Optional, Tuple
import threading

from .session_manager import SAMAISessionManager
from .data_extractor import SAMAIDataExtractor
from .download_manager import SAMAIDownloadManager


class ConsejoEstadoScraper:
    """Scraper principal para el sistema SAMAI del Consejo de Estado"""

    def __init__(self):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = Path(f"logs/consejo_estado_{self.timestamp}")
        self.pdf_dir = Path("descargas_consejo_estado")
        self.setup_directories()
        self.setup_logging()

        # Componentes
        self.session_manager = SAMAISessionManager()
        self.data_extractor = SAMAIDataExtractor()
        self.download_manager = SAMAIDownloadManager(self.pdf_dir)

        # Estado
        self.all_results = []
        self.download_stats = {
            'total': 0,
            'exitosas': 0,
            'fallidas': 0,
            'errores': []
        }

    def setup_directories(self):
        """Crear directorios necesarios"""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(exist_ok=True)

    def setup_logging(self):
        """Configurar sistema de logging"""
        log_file = self.log_dir / "consejo_estado_scraping.log"

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logging.basicConfig(
            level=logging.INFO,
            handlers=[file_handler, console_handler]
        )

        self.logger = logging.getLogger(__name__)

    def search_and_download(self, filters: dict, download_pdfs: bool = True,
                            max_results: Optional[int] = None, max_workers: int = 3,
                            cancel_event: threading.Event = None) -> List[Dict]:
        """
        Función principal de búsqueda y descarga

        Args:
            filters: Diccionario con filtros de búsqueda
            download_pdfs: Si descargar los PDFs
            max_results: Límite de resultados
            max_workers: Workers para descargas paralelas
            cancel_event: Evento de cancelación

        Returns:
            Lista de resultados procesados
        """
        start_time = datetime.now()

        self.logger.info("=" * 70)
        self.logger.info("🚀 INICIANDO SCRAPER CONSEJO DE ESTADO - SAMAI")
        self.logger.info("=" * 70)
        self.logger.info(f"Filtros: {json.dumps(filters, indent=2, ensure_ascii=False)}")
        self.logger.info(f"Descargar PDFs: {download_pdfs}")
        self.logger.info(f"Límite resultados: {max_results if max_results else 'Sin límite'}")

        try:
            # Fase 1: Búsqueda inicial y obtención del total
            self.logger.info("\n📡 FASE 1: Búsqueda inicial...")

            pagina_inicial = 0
            url_busqueda = self.session_manager.construir_url_busqueda(
                filters['sala_decision'],
                filters['fecha_desde'],
                filters['fecha_hasta'],
                pagina_inicial
            )

            html_inicial = self.session_manager.obtener_pagina(url_busqueda)
            if not html_inicial:
                self.logger.error("❌ Error obteniendo página inicial")
                return []

            # Extraer información de paginación
            total_resultados, resultados_por_pagina = self.data_extractor.extraer_info_paginacion(html_inicial)

            if total_resultados == 0:
                self.logger.info("No se encontraron resultados")
                return []

            # Limitamos a 2 páginas máximo por ahora
            MAX_PAGINAS_PERMITIDAS = 2

            total_paginas = (total_resultados + resultados_por_pagina - 1) // resultados_por_pagina

            # Si no se detectó información de paginación, intentar con 2 páginas
            if total_resultados == 0:
                # Verificar si hay resultados en la página inicial
                documentos_iniciales = self.data_extractor.extraer_documentos_con_tokens(html_inicial)
                if documentos_iniciales:
                    self.logger.info(f"Se encontraron {len(documentos_iniciales)} documentos en la primera página")
                    total_resultados = len(documentos_iniciales) * 2  # Estimación
                    total_paginas = 2
                    resultados_por_pagina = len(documentos_iniciales)
                else:
                    self.logger.info("No se encontraron resultados")
                    return []

            # Aplicar límite de páginas
            if total_paginas > MAX_PAGINAS_PERMITIDAS:
                self.logger.info(f"⚠️ Limitando a {MAX_PAGINAS_PERMITIDAS} páginas (de {total_paginas} totales)")
                total_paginas = MAX_PAGINAS_PERMITIDAS

            self.logger.info(f"📊 Total resultados estimados: {total_resultados}")
            self.logger.info(f"📄 Páginas a procesar: {total_paginas}")
            self.logger.info(f"📋 Resultados por página: {resultados_por_pagina}")

            # Aplicar límite si existe
            if max_results and max_results < total_resultados:
                total_resultados = max_results
                total_paginas = (total_resultados + resultados_por_pagina - 1) // resultados_por_pagina
                self.logger.info(f"🎯 Limitando a {max_results} resultados ({total_paginas} páginas)")

            # Guardar manifiesto
            self.save_manifest(filters, total_resultados, total_paginas)

            # Fase 2: Procesamiento de páginas
            self.logger.info("\n🔄 FASE 2: Procesamiento de páginas...")

            resultados_procesados = 0

            for pagina_actual in range(total_paginas):
                if cancel_event and cancel_event.is_set():
                    self.logger.info("🛑 Proceso cancelado por el usuario")
                    break

                if max_results and resultados_procesados >= max_results:
                    self.logger.info(f"✅ Se alcanzó el límite de {max_results} resultados")
                    break

                self.logger.info(f"\n📄 PÁGINA {pagina_actual + 1}/{total_paginas}")
                self.logger.info("-" * 50)

                # Obtener página (la primera ya la tenemos)
                if pagina_actual == 0:
                    html_pagina = html_inicial
                else:
                    url_pagina = self.session_manager.construir_url_busqueda(
                        filters['sala_decision'],
                        filters['fecha_desde'],
                        filters['fecha_hasta'],
                        pagina_actual
                    )

                    html_pagina = self.session_manager.obtener_pagina(url_pagina)
                    if not html_pagina:
                        self.logger.error(f"❌ Error obteniendo página {pagina_actual + 1}")
                        continue

                # Extraer documentos de la página
                documentos = self.data_extractor.extraer_documentos_con_tokens(html_pagina)

                # Validar y limpiar documentos
                documentos_validos = []
                for idx, doc in enumerate(documentos):
                    # Calcular posición global del documento
                    posicion_global = (pagina_actual * resultados_por_pagina) + idx + 1
                    doc['posicion_busqueda'] = posicion_global
                    doc['pagina'] = pagina_actual + 1
                    doc['posicion_en_pagina'] = idx + 1

                    # Validar que tenga datos mínimos
                    if doc.get('token') and doc.get('numero_proceso'):
                        documentos_validos.append(doc)
                        self.logger.debug(f"Documento válido: Posición {posicion_global} - {doc['numero_proceso']}")
                    else:
                        self.logger.warning(f"Documento inválido en posición {idx + 1}")

                self.logger.info(f"Documentos encontrados: {len(documentos_validos)}")

                # Aplicar límite si es necesario
                if max_results:
                    espacio_disponible = max_results - resultados_procesados
                    documentos_validos = documentos_validos[:espacio_disponible]

                # Procesar descargas si está habilitado
                if download_pdfs and documentos_validos:
                    self.logger.info(f"📥 Procesando {len(documentos_validos)} descargas...")

                    for doc in documentos_validos:
                        if cancel_event and cancel_event.is_set():
                            break

                        resultado_descarga = self.download_manager.procesar_documento(
                            doc,
                            self.session_manager.session
                        )

                        # Actualizar estadísticas
                        self.download_stats['total'] += 1
                        if resultado_descarga['exitoso']:
                            self.download_stats['exitosas'] += 1
                            doc['descarga_exitosa'] = True
                            doc['archivo_descargado'] = resultado_descarga['archivo']
                            doc['tamaño_archivo'] = resultado_descarga['tamaño']
                        else:
                            self.download_stats['fallidas'] += 1
                            doc['descarga_exitosa'] = False
                            doc['error_descarga'] = resultado_descarga['error']
                            self.download_stats['errores'].append({
                                'documento': doc['numero_proceso'],
                                'posicion': doc['posicion_busqueda'],
                                'error': resultado_descarga['error']
                            })

                        # Pausa entre descargas
                        time.sleep(2)

                # Agregar a resultados
                self.all_results.extend(documentos_validos)
                resultados_procesados += len(documentos_validos)

                self.logger.info(f"✅ Página procesada. Total acumulado: {resultados_procesados}")

                # Guardar progreso cada 5 páginas
                if (pagina_actual + 1) % 5 == 0:
                    self.save_results()

                # Pausa entre páginas
                if pagina_actual < total_paginas - 1:
                    time.sleep(1)

            # Fase 3: Guardar resultados finales
            self.logger.info("\n💾 FASE 3: Guardando resultados finales...")
            self.save_results()

            # Generar reporte
            elapsed_time = (datetime.now() - start_time).total_seconds()
            self.generate_final_report(elapsed_time)

            self.logger.info("\n" + "=" * 70)
            self.logger.info("✅ PROCESO COMPLETADO")
            self.logger.info(f"📄 Documentos procesados: {len(self.all_results)}")
            if download_pdfs:
                self.logger.info(f"📥 Descargas exitosas: {self.download_stats['exitosas']}")
                self.logger.info(f"❌ Descargas fallidas: {self.download_stats['fallidas']}")
            self.logger.info(f"⏱️  Tiempo total: {elapsed_time:.1f} segundos")
            self.logger.info("=" * 70)

            return self.all_results

        except Exception as e:
            self.logger.error(f"❌ Error crítico: {e}", exc_info=True)
            return self.all_results

    def save_manifest(self, filters: dict, total_resultados: int, total_paginas: int):
        """Guardar manifiesto de la búsqueda"""
        manifest = {
            'timestamp': self.timestamp,
            'fecha_busqueda': datetime.now().isoformat(),
            'filtros': filters,
            'total_resultados': total_resultados,
            'total_paginas': total_paginas,
            'archivos_generados': {
                'log': str(self.log_dir / 'consejo_estado_scraping.log'),
                'resultados_json': str(self.log_dir / 'resultados.json'),
                'resultados_csv': str(self.log_dir / f'consejo_estado_{self.timestamp}.csv'),
                'carpeta_pdfs': str(self.pdf_dir)
            }
        }

        manifest_path = self.log_dir / 'manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def save_results(self):
        """Guardar resultados en JSON y CSV"""
        # JSON
        json_path = self.log_dir / 'resultados.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.all_results, f, ensure_ascii=False, indent=2)

        # CSV
        if self.all_results:
            import csv
            csv_path = self.log_dir / f'consejo_estado_{self.timestamp}.csv'

            fieldnames = [
                'posicion_busqueda', 'pagina', 'posicion_en_pagina',
                'numero_proceso', 'interno', 'titular', 'sala_decision',
                'fecha_proceso', 'fecha_providencia', 'tipo_providencia',
                'clase_proceso', 'actor', 'demandado',
                'descarga_exitosa', 'archivo_descargado', 'error_descarga'
            ]

            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(self.all_results)

    def generate_final_report(self, elapsed_time: float):
        """Generar reporte final"""
        report = {
            'resumen': {
                'total_documentos': len(self.all_results),
                'descargas_exitosas': self.download_stats['exitosas'],
                'descargas_fallidas': self.download_stats['fallidas'],
                'tasa_exito': f"{(self.download_stats['exitosas'] / self.download_stats['total'] * 100):.1f}%"
                if self.download_stats['total'] > 0 else "0%",
                'tiempo_total': f"{elapsed_time:.1f} segundos"
            },
            'errores_descarga': self.download_stats['errores'][:10],  # Primeros 10 errores
            'timestamp_inicio': self.timestamp,
            'timestamp_fin': datetime.now().isoformat()
        }

        report_path = self.log_dir / 'reporte_final.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)