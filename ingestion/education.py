"""
ingestion/education.py
Télécharge l'annuaire des établissements scolaires pour Paris (75).
Source : data.education.gouv.fr
Compétence validée : C2.3
"""
import json
import sys
from pathlib import Path

import requests
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR

OUTPUT = BRONZE_DIR / "education_paris.json"

URL = (
    "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "fr-en-annuaire-education/exports/json"
    "?lang=fr&refine=code_departement%3A075&limit=5000"
)


def run():
    logger.info("Ingestion établissements scolaires (Paris)…")

    if OUTPUT.exists():
        logger.info(f"  {OUTPUT.name} déjà présent, skip")
        return True

    try:
        r = requests.get(URL, timeout=60)
        r.raise_for_status()
        data = r.json()
        count = len(data) if isinstance(data, list) else 0
        OUTPUT.write_text(json.dumps(data, ensure_ascii=False))
        logger.success(f"  ✓ {count} établissements → {OUTPUT.name}")
        return True
    except Exception as e:
        logger.error(f"  Échec : {e}")
        return False


if __name__ == "__main__":
    run()
