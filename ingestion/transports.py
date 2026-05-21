"""
ingestion/transports.py
Télécharge les arrêts de transport Île-de-France (métro, RER, bus) via IDFM.
Source : data.iledefrance-mobilites.fr
Compétence validée : C2.3
"""
import json
import sys
from pathlib import Path

import requests
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR

OUTPUT = BRONZE_DIR / "transports_idf_arrets.json"

# API IDFM — export JSON des arrêts parisiens
URL = (
    "https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/"
    "arrets-transporteurs-idf/exports/json"
    "?lang=fr&refine=id_commune%3A75056&limit=10000"
)

URL_FALLBACK = (
    "https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/"
    "emplacement-des-gares-idf/exports/json?lang=fr&limit=5000"
)


def run():
    logger.info("Ingestion arrêts de transport (IDFM)…")

    if OUTPUT.exists():
        logger.info(f"  {OUTPUT.name} déjà présent, skip")
        return True

    for url, label in [(URL, "principale"), (URL_FALLBACK, "fallback")]:
        try:
            logger.info(f"  Tentative source {label}…")
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            data = r.json()
            count = len(data) if isinstance(data, list) else len(data.get("results", []))
            OUTPUT.write_text(json.dumps(data, ensure_ascii=False))
            logger.success(f"  ✓ {count} arrêts sauvegardés → {OUTPUT.name}")
            return True
        except Exception as e:
            logger.warning(f"  Source {label} échouée : {e}")

    logger.error("  Toutes les sources IDFM ont échoué")
    return False


if __name__ == "__main__":
    run()
