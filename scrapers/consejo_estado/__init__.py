# scrapers/consejo_estado/__init__.py
from .scraper import ConsejoEstadoScraper

from .data_extractor import SAMAIDataExtractor


__all__ = [
    'ConsejoEstadoScraper',
    'SAMAIDataExtractor'

]