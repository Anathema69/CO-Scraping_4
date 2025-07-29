# scrapers/jurisprudencia/navigation_handler.py
"""
Manejador de navegación simplificado para el scraper judicial
Mantiene solo la lógica de navegación sin gestión compleja de sesiones
"""
import time
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime


class NavigationHandler:
    """Gestiona la navegación entre páginas con manejo robusto de errores"""

    def __init__(self, scraper_instance):
        """
        Args:
            scraper_instance: Instancia del scraper principal que contiene la sesión
        """
        self.scraper = scraper_instance
        self.logger = logging.getLogger(__name__)

        # Configuración de navegación
        self.max_retries = 3
        self.retry_delay_base = 2.0
        self.max_consecutive_failures = 3

        # Estado de navegación
        self.pages_navigated = 0
        self.consecutive_failures = 0
        self.navigation_errors = []

        # Botones de navegación
        self.nav_buttons = {
            'first': 'resultForm:j_idt257',
            'prev': 'resultForm:j_idt258',
            'next': 'resultForm:j_idt259',
            'last': 'resultForm:j_idt260'
        }

    def navigate_and_collect(self, total_results: int, max_results: Optional[int] = None,
                             process_callback=None, cancel_event=None) -> List[Dict]:
        """
        Navegar por todas las páginas y recolectar datos

        Args:
            total_results: Total de resultados a navegar
            max_results: Límite máximo de resultados
            process_callback: Función a llamar con cada página de datos
            cancel_event: Evento de cancelación

        Returns:
            Lista con todos los resultados recolectados
        """
        all_results = []
        target_results = min(total_results, max_results) if max_results else total_results
        current_page = 1

        self.logger.info(f"🎯 Iniciando navegación: {target_results} resultados objetivo")

        # La primera página ya fue procesada en el scraper principal
        # así que empezamos desde la página 2

        while len(all_results) < target_results:
            # Verificar cancelación
            if cancel_event and cancel_event.is_set():
                self.logger.info("🛑 Navegación cancelada por el usuario")
                break

            # Navegar a siguiente página
            success, page_html = self._navigate_to_next_with_retry()

            if not success:
                self.consecutive_failures += 1
                self.logger.error(f"❌ Fallo navegación a página {current_page + 1}")

                if self.consecutive_failures >= self.max_consecutive_failures:
                    self.logger.error("💥 Demasiados fallos consecutivos, terminando navegación")
                    break
                else:
                    current_page += 1
                    continue

            # Resetear contador de fallos
            self.consecutive_failures = 0

            # Extraer datos de la página
            page_data = self.scraper.extract_jurisprudence_data(page_html)

            if not page_data:
                self.logger.warning(f"⚠️ Sin datos en página {current_page + 1}")
            else:
                # Filtrar duplicados
                new_records = self._filter_duplicates(page_data, all_results)

                if new_records:
                    all_results.extend(new_records)
                    if process_callback:
                        process_callback(new_records)

                    self.logger.info(
                        f"📄 Página {current_page + 1}: {len(new_records)} nuevos, "
                        f"Total: {len(all_results)}/{target_results}"
                    )

            current_page += 1
            self.pages_navigated += 1

            # Pausa adaptativa
            self._adaptive_delay()

        self.logger.info(f"✅ Navegación completada: {len(all_results)} registros recolectados")
        return all_results

    def _navigate_to_next_with_retry(self) -> Tuple[bool, Optional[str]]:
        """Navegar a la siguiente página con reintentos"""
        for attempt in range(self.max_retries):
            try:
                success, html = self.scraper.navigate_to_next(self.scraper.viewstate)

                if success:
                    return True, html

                self.logger.warning(f"⚠️ Intento {attempt + 1}/{self.max_retries} falló")

            except Exception as e:
                self.logger.error(f"❌ Error en intento {attempt + 1}: {e}")
                self.navigation_errors.append({
                    'timestamp': datetime.now().isoformat(),
                    'error': str(e),
                    'attempt': attempt + 1
                })

            if attempt < self.max_retries - 1:
                delay = self.retry_delay_base * (attempt + 1)
                self.logger.info(f"⏳ Esperando {delay}s antes del siguiente intento...")
                time.sleep(delay)

        return False, None

    def _filter_duplicates(self, new_data: List[Dict], existing_data: List[Dict]) -> List[Dict]:
        """Filtrar registros duplicados"""
        existing_ids = {record.get('id') for record in existing_data if record.get('id')}
        filtered = []

        for record in new_data:
            if record.get('id') and record['id'] not in existing_ids:
                filtered.append(record)
            else:
                self.logger.debug(f"Duplicado filtrado: {record.get('id')}")

        return filtered

    def _adaptive_delay(self):
        """Pausa adaptativa basada en el estado"""
        if self.consecutive_failures > 0:
            # Más tiempo si hay fallos
            delay = 2.0 + (self.consecutive_failures * 0.5)
        else:
            # Delay normal
            delay = 0.8

        time.sleep(delay)

    def get_navigation_stats(self) -> dict:
        """Obtener estadísticas de navegación"""
        return {
            'pages_navigated': self.pages_navigated,
            'consecutive_failures': self.consecutive_failures,
            'total_errors': len(self.navigation_errors),
            'last_error': self.navigation_errors[-1] if self.navigation_errors else None
        }