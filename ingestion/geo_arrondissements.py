"""
ingestion/geo_arrondissements.py
Télécharge les contours GeoJSON des 20 arrondissements parisiens.
Source : geo.api.gouv.fr
Compétence validée : C2.3 (collecte multi-sources)
"""
import json
import sys
from pathlib import Path

import requests
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR

OUTPUT = BRONZE_DIR / "geo_arrondissements.geojson"

# URL alternative fiable (OpenDataSoft Paris)
URL = (
    "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/"
    "arrondissements/exports/geojson?lang=fr"
)
URL_FALLBACK = "https://geo.api.gouv.fr/communes?codeDepartement=75&format=geojson&geometry=contour"


def fetch_geo_arrondissements() -> dict:
    logger.info("Téléchargement des contours arrondissements…")
    try:
        r = requests.get(URL, timeout=30)
        r.raise_for_status()
        data = r.json()
        logger.success(f"  {len(data.get('features', []))} features récupérées (source principale)")
        return data
    except Exception as e:
        logger.warning(f"  Source principale échouée ({e}), tentative fallback…")
        r = requests.get(URL_FALLBACK, timeout=30)
        r.raise_for_status()
        data = r.json()
        logger.success(f"  {len(data.get('features', []))} features récupérées (fallback)")
        return data


def run():
    data = fetch_geo_arrondissements()
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    logger.info(f"  Sauvegardé → {OUTPUT}")
    return True


if __name__ == "__main__":
    run()
