"""Source-specific scrapers. Importing this package registers all of them."""

from jd_collector.scrapers.base import SCRAPERS, BaseScraper, build_scraper, register
from jd_collector.scrapers import accenture, ashby, css, greenhouse, jsonld, lever, smartrecruiters  # noqa: F401

__all__ = ["SCRAPERS", "BaseScraper", "build_scraper", "register"]
